# TTL (ttlSecondsAfterFinished) 테스트 시나리오

## 테스트 목표

`ttlSecondsAfterFinished: 60` 설정이 실제로 **Failed TrainJob**을 60초 후 자동 삭제하는지 확인

## 테스트 환경 요구사항

- Kubernetes 클러스터 (v1.23+)
- Kubeflow Training Operator 설치
- `kubectl` CLI 접근 권한
- `jq` (JSON 파싱용, 선택사항)

## 테스트 단계

### 1단계: 기본 설정 확인

```bash
# Namespace 생성
kubectl create namespace kubeflow-system

# Runtime 리소스 확인
kubectl get clustertrainingruntimes -o wide
kubectl describe ctr pytorch-runtime
kubectl describe ctr tensorflow-runtime
```

**예상 결과**:
```
NAME              FRAMEWORK     AGE
pytorch-runtime   pytorch       <recent>
tensorflow-runtime tensorflow   <recent>
```

### 2단계: 실패 TrainJob 생성 (PyTorch)

```yaml
# pytorch-test-fail.yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: pytorch-fail-test
  namespace: kubeflow-system
spec:
  runtimeRef:
    name: pytorch-runtime
  trainer:
    image: pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime
    numNodes: 1
    command:
      - bash
      - -c
      - |
        echo "이 작업은 의도적으로 실패합니다"
        exit 1  # ← 즉시 실패
    resourcesPerNode:
      limits:
        cpu: "1"
        memory: "2Gi"
      requests:
        cpu: "1"
        memory: "2Gi"
  podTemplateOverrides:
    - targetJobs:
        - name: node
      spec:
        initContainers: []
        containers:
          - name: node
```

**적용**:
```bash
kubectl apply -f pytorch-test-fail.yaml
```

### 3단계: 실패 상태 모니터링

```bash
# 실시간 모니터링 (터미널 1)
watch -n 1 'kubectl get trainjob -n kubeflow-system'

# 상세 정보 (터미널 2)
kubectl describe trainjob pytorch-fail-test -n kubeflow-system

# Pod 상태 (터미널 3)
watch -n 1 'kubectl get pods -n kubeflow-system -l trainer.kubeflow.org/job-name=pytorch-fail-test'
```

### 4단계: TTL 작동 확인

#### t=0~10초: 실패 상태 확인
```bash
kubectl get trainjob pytorch-fail-test -n kubeflow-system -o json | \
  jq '.status.conditions[] | select(.type=="Failed")'
```

**예상**:
```json
{
  "type": "Failed",
  "status": "True",
  "lastProbeTime": "2024-11-10T10:43:00Z",
  "lastTransitionTime": "2024-11-10T10:43:05Z",
  "reason": "BackoffLimitExceeded"
}
```

#### t=10~60초: completionTime 확인
```bash
kubectl get trainjob pytorch-fail-test -n kubeflow-system -o json | \
  jq '.status | {completionTime, startTime}'
```

**예상**:
```json
{
  "completionTime": "2024-11-10T10:43:05Z",  # ← 설정될 것
  "startTime": "2024-11-10T10:43:00Z"
}
```

#### t=60~70초: 자동 삭제 확인
```bash
# 60초 후 실행
kubectl get trainjob -n kubeflow-system

# 또는 구체적으로
kubectl get trainjob pytorch-fail-test -n kubeflow-system
```

**예상**:
```
# t=60초 이후
Error from server (NotFound): trainjobs.trainer.kubeflow.org "pytorch-fail-test" not found
```

### 5단계: Pod 상태 확인

```bash
# 60초 전
kubectl get pods -n kubeflow-system -l trainer.kubeflow.org/trainjob-name=pytorch-fail-test

# 60초 후
kubectl get pods -n kubeflow-system -l trainer.kubeflow.org/trainjob-name=pytorch-fail-test
```

**예상**:
- 60초 전: Pod 존재
- 60초 후: Pod 없음 (또는 Terminating 상태)

## 테스트 결과 기록

### 테스트 1: PyTorch Failed TrainJob

| 항목 | 예상 | 실제 | 상태 |
|------|------|------|------|
| 작업 실패 감지 | ✓ | ? | - |
| completionTime 설정 | ✓ | ? | - |
| TTL 카운트 시작 | ✓ | ? | - |
| 60초 후 TrainJob 삭제 | ✓ | ? | - |
| 60초 후 Pod 삭제 | ✓ | ? | - |

### 테스트 2: TensorFlow Failed TrainJob

동일한 과정을 TensorFlow용으로 반복

```yaml
# tensorflow-test-fail.yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: tensorflow-fail-test
  namespace: kubeflow-system
spec:
  runtimeRef:
    name: tensorflow-runtime
  trainer:
    image: tensorflow/tensorflow:2.15.0-gpu
    numNodes: 1
    command:
      - bash
      - -c
      - |
        echo "이 작업은 의도적으로 실패합니다"
        exit 1
    resourcesPerNode:
      limits:
        cpu: "1"
        memory: "2Gi"
      requests:
        cpu: "1"
        memory: "2Gi"
  podTemplateOverrides:
    - targetJobs:
        - name: node
      spec:
        initContainers: []
        containers:
          - name: node
```

## 주의사항

⚠️ **중요**: 테스트 후 `ttlSecondsAfterFinished` 값을 프로덕션에 적합한 값으로 변경하세요:
- 개발: 300-600초 (5-10분)
- 스테이징: 3600초 (1시간)
- 프로덕션: 86400초 (24시간) 권장

## 문제 해결

### 60초 후에도 TrainJob이 남아있는 경우

1. **원인 가능성**:
   - TTL 컨트롤러가 비활성화됨
   - Kubernetes 버전이 1.23 미만
   - finalize가 설정되어 있음

2. **확인 방법**:
   ```bash
   # TTL 컨트롤러 로그 확인
   kubectl logs -n kube-system -l app=ttl-after-finished-controller
   
   # TrainJob의 finalizer 확인
   kubectl get trainjob pytorch-fail-test -n kubeflow-system -o json | jq '.metadata.finalizers'
   ```

### Failed 상태가 되지 않는 경우

1. **원인 가능성**:
   - initContainer 실패로 Pod이 생성되지 않음
   - 리소스 부족으로 pending 상태 유지

2. **확인 방법**:
   ```bash
   # Pod 상태 상세 확인
   kubectl describe pod <pod-name> -n kubeflow-system
   
   # 이벤트 확인
   kubectl get events -n kubeflow-system --sort-by='.lastTimestamp'
   ```

## 참고 자료

- [Kubernetes Job TTL Documentation](https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/)
- [Kubeflow Training Operator](https://www.kubeflow.org/docs/components/training/)
