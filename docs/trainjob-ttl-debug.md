# TrainJob TTL 문제 진단 및 해결

## 현재 증상
```
✅ Pod 삭제됨
❌ TrainJob 남음 (COMPLETED 상태)
```

## 원인 분석

### 1단계: TrainJob 상태 확인

```bash
# TrainJob 상세 조회
kubectl get trainjob <name> -n kubeflow-system -o json

# 확인할 항목:
# - .metadata.finalizers 존재 여부
# - .status.conditions (type: Succeeded/Completed)
# - .status.completionTime 존재 여부
# - .status.startTime
```

**예상 출력**:
```json
{
  "metadata": {
    "name": "pytorch-test",
    "finalizers": [],  # ← 없어야 함
    "creationTimestamp": "2024-11-10T10:43:00Z",
    "deletionTimestamp": null  # ← null이면 정상
  },
  "status": {
    "conditions": [
      {
        "type": "Succeeded",  # 또는 "Completed"
        "status": "True",
        "completionTime": "2024-11-10T10:43:05Z"  # ← 반드시 있어야 함
      }
    ],
    "startTime": "2024-11-10T10:43:00Z",
    "completionTime": "2024-11-10T10:43:05Z"
  }
}
```

### 2단계: ReplicatedJob 상태 확인

```bash
# ReplicatedJob 조회 (Kubeflow Training Operator가 자동 생성)
kubectl get replicatedjobs -n kubeflow-system -o wide

# 삭제 시 문제가 없는지 확인
kubectl get replicatedjobs <name> -n kubeflow-system -o json | \
  jq '{metadata: .metadata, status: .status}'
```

### 3단계: Kubernetes Job 상태 확인

```bash
# 실제 Job 객체 확인
kubectl get jobs -n kubeflow-system -o wide

# Job의 TTL 설정 확인
kubectl get jobs <job-name> -n kubeflow-system -o json | \
  jq '{spec: {ttlSecondsAfterFinished: .spec.ttlSecondsAfterFinished}, status: {completionTime: .status.completionTime}}'
```

**예상**: ttlSecondsAfterFinished: 60 설정되어 있어야 함

### 4단계: finalizer 확인

```bash
# TrainJob의 finalizer 확인
kubectl get trainjob <name> -n kubeflow-system -o json | jq '.metadata.finalizers'

# 만약 finalizer가 있다면 제거 필요
kubectl patch trainjob <name> -n kubeflow-system -p '{"metadata":{"finalizers":null}}'
```

## 원인별 해결책

### 원인 1: TrainJob의 finalizer가 설정되어 있음

**증상**: COMPLETED 상태이지만 객체가 삭제되지 않음

**해결**:
```bash
# finalizer 제거
kubectl patch trainjob <name> -n kubeflow-system --type merge \
  -p '{"metadata":{"finalizers":null}}'
```

### 원인 2: ReplicatedJob의 TTL이 작동하지 않음

**증상**: Job은 있는데 TTL이 적용되지 않음

**확인**:
```bash
# Kubeflow Training Operator 로그 확인
kubectl logs -n kubeflow-system deployment/training-operator \
  | grep -i "ttl\|garbage\|cleanup" | tail -20
```

**해결**: 
- Kubeflow Training Operator가 TTL을 지원하지 않을 수 있음
- `cleanupTTL` 또는 다른 정책이 있는지 확인 필요

### 원인 3: completionTime이 설정되지 않음

**증상**: Job이 Succeeded 상태이지만 completionTime 없음

**확인**:
```bash
kubectl get jobs -n kubeflow-system -o json | \
  jq '.items[] | {name: .metadata.name, completionTime: .status.completionTime, succeeded: .status.succeeded}'
```

**해결**: 
- Kubeflow Training Operator의 Job 생성 정책 확인
- Job 컨트롤러 로그 확인

## 종합 진단 스크립트

```bash
#!/bin/bash
TRAINJOB_NAME=$1
NAMESPACE=${2:-kubeflow-system}

echo "=== TrainJob 상태 ==="
kubectl get trainjob $TRAINJOB_NAME -n $NAMESPACE -o json | \
  jq '{
    name: .metadata.name,
    phase: .status.phase,
    conditions: .status.conditions,
    finalizers: .metadata.finalizers,
    completionTime: .status.completionTime,
    creationTime: .metadata.creationTimestamp
  }'

echo ""
echo "=== ReplicatedJob 상태 ==="
kubectl get replicatedjobs -n $NAMESPACE -l trainer.kubeflow.org/job-name=$TRAINJOB_NAME -o json | \
  jq '.items[] | {
    name: .metadata.name,
    finalizers: .metadata.finalizers,
    phase: .status.phase
  }'

echo ""
echo "=== Kubernetes Job 상태 ==="
kubectl get jobs -n $NAMESPACE -l trainer.kubeflow.org/job-name=$TRAINJOB_NAME -o json | \
  jq '.items[] | {
    name: .metadata.name,
    ttlSecondsAfterFinished: .spec.ttlSecondsAfterFinished,
    succeeded: .status.succeeded,
    failed: .status.failed,
    completionTime: .status.completionTime,
    startTime: .status.startTime
  }'

echo ""
echo "=== Pod 상태 ==="
kubectl get pods -n $NAMESPACE -l trainer.kubeflow.org/job-name=$TRAINJOB_NAME
```

## Kubeflow Training Operator 특성

### TTL 지원 여부

Kubeflow Training Operator는 **ReplicatedJob**이라는 커스텀 리소스를 생성합니다:

```yaml
apiVersion: kubeflow.org/v1
kind: ReplicatedJob  # ← Kubernetes의 표준 Job이 아님
metadata:
  name: pytorch-test-node-0
spec:
  template:
    spec:
      ttlSecondsAfterFinished: 60  # ← 표준 Kubernetes TTL
```

**문제**: ReplicatedJob 레벨의 TTL 지원 여부는 Training Operator 버전에 따라 다를 수 있음

### 대안 솔루션

만약 TTL이 작동하지 않는다면, Kubeflow 제공 옵션 사용:

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: pytorch-test
spec:
  runtimeRef:
    name: pytorch-runtime
  cleanupPolicy:  # ← Kubeflow의 정책 (있는 경우)
    ttlSecondsAfterFinished: 60
  # ... 나머지 설정
```

또는 컨트롤러 수준의 정책:

```bash
# Training Operator Helm 값
trainingOperator:
  config:
    cleanupTTL: 60
    # OR
    jobRetentionPolicy: "delete_on_completion"
```

## 다음 단계

1. **즉시 진단**: 위의 진단 스크립트 실행
2. **로그 확인**: Kubeflow Training Operator 로그 검토
3. **Operator 버전 확인**: `kubectl get deployment training-operator -n kubeflow-system -o yaml`
4. **공식 이슈 검색**: https://github.com/kubeflow/training-operator/issues?q=ttl

## 참고

- [Kubeflow Training Operator GitHub](https://github.com/kubeflow/training-operator)
- [ReplicatedJob API](https://github.com/kubeflow/training-operator/blob/master/pkg/apis/kubeflow.org/v1/replicated_job_types.go)
