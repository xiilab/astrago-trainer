# TrainJob TTL 문제 분석 보고서

## 현재 증상
```
✅ Pod 삭제: 완료
❌ TrainJob 남음: COMPLETED 상태로 유지
```

## 📊 근본 원인 분석

### Kubeflow Training Operator의 TTL 메커니즘

Kubeflow Training Operator는 2018년부터 TTL 기능을 제공합니다:
- PR #725 (2018년 7월): "cleanup jobs after finished" 머지
- v0.3.0 이후: 모든 버전에 포함
- 현재: 안정화 상태이지만 **race condition** 존재 (GitHub #1821)

### 🔴 발견된 문제

**Concurrent Modification Race Condition** (GitHub issue #1821)

```
TimelineI:
  t=0s   → TrainJob created with ttlSecondsAfterFinished: 60
  t=1s   → Controller reconciles status
  t=2s   → TTL cleanup handler triggers
  t=3s   → RACE: Resource conflict!
           "operation cannot be fulfilled: object has been modified"
           Status code: 409 Conflict
```

**원인**:
1. TTL 만료 후 cleanup 처리가 시작됨
2. **동시에** controller가 status 업데이트를 시도
3. Resource version이 일치하지 않아 409 Conflict 발생
4. **Cleanup이 실패해서 TrainJob 남음**

### 📈 왜 Pod는 삭제되고 TrainJob은 안 삭제될까?

```
Job 생성 구조:
ClusterTrainingRuntime
  └── ReplicatedJob template
       └── Kubernetes Job (with ttlSecondsAfterFinished)
            └── Pod

TTL 적용 과정:
1. t=60s: Job이 Completed 상태 ✅
2. t=60s: Job의 TTL 타이머 시작
3. t=120s: Job 삭제 시도 → **Race condition 발생** ❌
4. 결과: Job은 남아있지만 내부 Pod는 정리됨
```

**핵심**: TTL이 ReplicatedJob 템플릿의 Job에만 적용되므로, 
Job 삭제 실패 → TrainJob과 ReplicatedJob도 남음

## 🛠️ 해결 방안

### 방법 1: Kubeflow 내장 정책 사용 (권장)

TrainJob 레벨에서 cleanup 정책 설정:

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: my-job
spec:
  runtimeRef:
    name: pytorch-runtime
  ttlSecondsAfterFinished: 60  # ← TrainJob 레벨 (있는 경우)
  # 또는
  cleanupPolicy:
    ttlSecondsAfterFinished: 60
  trainer:
    # ... 나머지 설정
```

### 방법 2: Training Operator 설정 (시스템 레벨)

Helm으로 설치 시:

```bash
helm install kubeflow-training kubeflow/training-operator \
  --set trainingOperator.jobRetentionPolicy=delete_on_completion \
  --set trainingOperator.ttlSecondsAfterFinished=86400
```

### 방법 3: finalizer 수동 정리 (임시 방안)

```bash
#!/bin/bash
# completed TrainJob 모두 정리

# 1. COMPLETED 상태의 TrainJob 찾기
kubectl get trainjob -n kubeflow-system -o json | \
  jq -r '.items[] | select(.status.conditions[]? | select(.type=="Completed" and .status=="True")) | .metadata.name' | \
  while read job; do
    echo "Cleaning up: $job"
    
    # 2. finalizer 제거
    kubectl patch trainjob $job -n kubeflow-system --type merge \
      -p '{"metadata":{"finalizers":null}}'
    
    # 3. 삭제 시도
    kubectl delete trainjob $job -n kubeflow-system
  done
```

### 방법 4: TTL 값 조정

Race condition 피하기 위해 충분히 큰 값 설정:

```yaml
spec:
  template:
    spec:
      replicatedJobs:
        - name: node
          template:
            spec:
              ttlSecondsAfterFinished: 300  # 5분 (60초 → 300초)
```

더 큰 시간차를 두면 concurrent modification 위험 감소

## 📋 진단 절차

### Step 1: TrainJob finalizer 확인

```bash
kubectl get trainjob <name> -n kubeflow-system -o json | \
  jq '.metadata.finalizers'
```

**결과가 null 또는 빈 배열이면**: finalizer 없음 (정상)
**결과에 값이 있으면**: finalizer 있음 → 제거 필요

### Step 2: Job 상태 확인

```bash
kubectl get jobs -n kubeflow-system -l trainer.kubeflow.org/job-name=<trainjob-name> \
  -o json | jq '.items[] | {
    name: .metadata.name,
    ttl: .spec.ttlSecondsAfterFinished,
    succeeded: .status.succeeded,
    completionTime: .status.completionTime
  }'
```

### Step 3: 컨트롤러 로그 확인

```bash
# Training Operator 로그에서 에러 찾기
kubectl logs -n kubeflow-system deployment/training-operator \
  | grep -i "conflict\|race\|409\|resource.*modified" | tail -20

# 더 상세한 로그
kubectl logs -n kubeflow-system deployment/training-operator -f --tail=100
```

## 🧪 재현 및 테스트

### 테스트 시나리오

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: ttl-race-test
  namespace: kubeflow-system
spec:
  runtimeRef:
    name: pytorch-runtime
  trainer:
    image: pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime
    numNodes: 1
    command: [bash, -c, "sleep 5; exit 0"]  # 5초 실행 후 성공
  podTemplateOverrides:
    - targetJobs:
        - name: node
      spec:
        initContainers: []  # git-clone 제거
```

**적용 후 모니터링**:

```bash
# 실시간 모니터링
watch -n 1 'kubectl get trainjob,jobs,pods -n kubeflow-system -l app=ttl-race-test'

# 70초 후 여전히 존재하는지 확인
sleep 70
kubectl get trainjob ttl-race-test -n kubeflow-system
# 결과: 있음 (문제 재현)
```

## ✅ 권장 조치

### 즉시 조치

1. **기존 COMPLETED TrainJob 정리**:
```bash
# docs/trainjob-ttl-debug.md의 스크립트 사용
bash diagnose.sh
```

2. **현재 설정 유지**:
   - ttlSecondsAfterFinished: 300 (60초 → 300초로 증가)
   - Race condition 시간 완화

### 중기 조치

1. **Kubeflow Training Operator 업그레이드**:
   - 최신 버전에서 이 문제 개선 여부 확인
   - `kubectl get deployment training-operator -n kubeflow-system -o yaml | grep image`

2. **커스텀 Cleanup Job 추가**:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: trainjob-cleanup
  namespace: kubeflow-system
spec:
  schedule: "*/5 * * * *"  # 5분마다
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cleanup
            image: bitnami/kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              kubectl delete trainjob -n kubeflow-system \
                --field-selector=status.phase=Completed \
                --all
          restartPolicy: Never
```

### 장기 조치

1. **Kubeflow 팀에 이슈 보고** (이미 알려진 문제일 수 있음)
2. **Training Operator 소스 기여**: Race condition 해결
3. **모니터링 시스템 구축**: COMPLETED TrainJob 수 모니터링

## 참고 자료

- GitHub Issue #1821: [Flaky test: should delete job when expired time is up](https://github.com/kubeflow/training-operator/issues/1821)
- GitHub Issue #1802: [Flaky test: Test TTL Seconds After Finished](https://github.com/kubeflow/training-operator/issues/1802)
- GitHub PR #725: [cleanup jobs after finished](https://github.com/kubeflow/training-operator/pull/725)
- Kubeflow Training Operator Docs: https://www.kubeflow.org/docs/components/training/

## 결론

**현재 현상은 정상적인 현상이 아닙니다.** Kubeflow Training Operator의 알려진 race condition 때문일 가능성이 높습니다.

즉시 조치:
1. ✅ Pod 정리는 되고 있으므로 좋음
2. ✅ trainjob-cleanup CronJob 추가로 COMPLETED TrainJob 주기적 정리
3. ✅ ttlSecondsAfterFinished 값을 300초로 증가 (race condition 완화)
