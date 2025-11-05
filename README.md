# Kubeflow Training Operator v2 - Backend Integration

분산 ML 학습을 위한 Kubeflow Training Operator v2 통합 가이드입니다.

## 📋 목차
- [개요](#개요)
- [핵심 개념](#핵심-개념)
- [디렉토리 구조](#디렉토리-구조)
- [Backend 통합 가이드](#backend-통합-가이드)
- [API 요청 예시](#api-요청-예시)
- [배포 및 테스트](#배포-및-테스트)

---

## 개요

### 지원 프레임워크
- **PyTorch**: 자동 환경변수 변환 (PET → PyTorch 표준)
- **TensorFlow**: 자동 TF_CONFIG 생성

### 사용자 경험
사용자는 **학습 코드만 작성**, 환경 설정은 자동화

### 멀티테넌트 지원
각 사용자 네임스페이스에 독립적인 리소스 생성

---

## 핵심 개념

### 왜 이런 구조인가?

**문제점**:
1. ConfigMap은 같은 네임스페이스에서만 마운트 가능
2. 사용자 네임스페이스가 동적으로 생성됨 (회원가입 시)
3. System ConfigMap을 미리 만들 수 없음

**해결책**:
Backend가 TrainJob 생성 시 필요한 ConfigMap도 함께 생성

### 리소스 구조

```
사용자 네임스페이스 (예: user-123)
├── System ConfigMap       # 환경 설정 스크립트 (Backend가 템플릿에서 생성)
├── User ConfigMap         # 사용자 학습 코드 (Backend가 동적 생성)
└── TrainJob              # 학습 작업 (Backend가 생성)
```

### 처리 흐름

```
사용자 요청 (학습 코드 + 설정)
    ↓
Backend API
    ↓
1. System ConfigMap 생성 (이미 있으면 skip)
2. User ConfigMap 생성
3. TrainJob 생성
    ↓
Kubernetes가 자동으로:
    - Pod 생성
    - 환경변수 설정
    - 학습 실행
```

---

## 디렉토리 구조

```
kubeflow-training-integration/
├── README.md                          # 이 문서
├── pytorch/
│   ├── pytorch-pet-setup.yaml         # System ConfigMap 템플릿
│   ├── pytorch-runtime-simple.yaml    # Runtime (관리자 설치)
│   ├── pytorch-train-script-configmap.yaml    # User ConfigMap 예시
│   └── pytorch-distributed-with-configmap.yaml # TrainJob 템플릿
└── tensorflow/
    ├── tensorflow-tf-config-generator.yaml     # System ConfigMap 템플릿
    ├── tensorflow-runtime.yaml                 # Runtime (관리자 설치)
    ├── tensorflow-train-script-configmap.yaml  # User ConfigMap 예시
    └── tensorflow-distributed-with-configmap.yaml # TrainJob 템플릿
```

### 파일 역할

| 파일 | 역할 | Backend 처리 |
|------|------|-------------|
| `*-runtime*.yaml` | Runtime 정의 | ❌ 관리자가 클러스터에 설치 |
| `*-pet-setup.yaml` | PyTorch 환경설정 템플릿 | ✅ 사용자 네임스페이스에 생성 |
| `*-tf-config-generator.yaml` | TensorFlow 환경설정 템플릿 | ✅ 사용자 네임스페이스에 생성 |
| `*-train-script-configmap.yaml` | User ConfigMap 예시 | ✅ 사용자 코드로 동적 생성 |
| `*-distributed-with-configmap.yaml` | TrainJob 템플릿 | ✅ 사용자 요청에 맞게 생성 |

---

## Backend 통합 가이드

### 필수 처리 3단계

#### 1단계: System ConfigMap 생성

**목적**: 환경 설정 스크립트를 사용자 네임스페이스에 생성

**PyTorch**:
```python
# 템플릿 파일: pytorch/pytorch-pet-setup.yaml
# 내용: PET 환경변수를 PyTorch 표준으로 변환하는 shell script

# Backend 처리
system_configmap = load_yaml('pytorch/pytorch-pet-setup.yaml')
system_configmap['metadata']['namespace'] = user_namespace

# Kubernetes API로 생성 (idempotent - 이미 있으면 skip)
try:
    create_configmap(system_configmap)
except AlreadyExistsError:
    pass  # 같은 사용자가 여러 TrainJob 생성 가능
```

**TensorFlow**:
```python
# 템플릿 파일: tensorflow/tensorflow-tf-config-generator.yaml
# 내용: TF_CONFIG JSON을 자동 생성하는 shell script

# Backend 처리 (PyTorch와 동일)
system_configmap = load_yaml('tensorflow/tensorflow-tf-config-generator.yaml')
system_configmap['metadata']['namespace'] = user_namespace
create_configmap(system_configmap)
```

**중요**: System ConfigMap은 **idempotent**입니다. 같은 사용자가 여러 TrainJob을 만들 수 있으므로 이미 존재하면 skip합니다.

---

#### 2단계: User ConfigMap 생성

**목적**: 사용자가 작성한 학습 코드를 ConfigMap으로 저장

```python
user_configmap = {
    "apiVersion": "v1",
    "kind": "ConfigMap",
    "metadata": {
        "name": f"{user_id}-train-script",  # 예: user123-train-script
        "namespace": user_namespace
    },
    "data": {
        "train.py": training_code  # 사용자가 업로드한 Python 코드
    }
}

create_configmap(user_configmap)
```

---

#### 3단계: TrainJob 생성

**목적**: 학습 작업 생성

```python
# 템플릿 파일 로드
trainjob = load_yaml('pytorch/pytorch-distributed-with-configmap.yaml')

# 동적 설정
trainjob['metadata']['name'] = f"{user_id}-job-{timestamp}"
trainjob['metadata']['namespace'] = user_namespace
trainjob['spec']['trainer']['numNodes'] = num_nodes
trainjob['spec']['trainer']['resourcesPerNode']['limits']['nvidia.com/gpu'] = str(gpu_per_node)
trainjob['spec']['trainer']['resourcesPerNode']['limits']['cpu'] = str(cpu_per_node)
trainjob['spec']['trainer']['resourcesPerNode']['limits']['memory'] = memory_per_node

# User ConfigMap 이름 연결
for override in trainjob['spec']['podTemplateOverrides']:
    for volume in override['spec']['volumes']:
        if volume['name'] == 'train-script':
            volume['configMap']['name'] = f"{user_id}-train-script"

# TrainJob 생성
create_custom_resource(
    group="trainer.kubeflow.org",
    version="v1alpha1",
    plural="trainjobs",
    namespace=user_namespace,
    body=trainjob
)
```

---

### 프레임워크별 차이점

#### PyTorch

**System ConfigMap**: `pytorch-pet-setup`
```bash
# Shell script 내용
export RANK=$PET_NODE_RANK
export WORLD_SIZE=$PET_NNODES
export MASTER_ADDR=$PET_MASTER_ADDR
export MASTER_PORT=$PET_MASTER_PORT
export LOCAL_RANK=0
```

**TrainJob command**:
```bash
source /shared/setup_pytorch_env.sh  # 환경변수 설정
python /workspace/scripts/train.py   # 사용자 코드 실행
```

#### TensorFlow

**System ConfigMap**: `tensorflow-tf-config-generator`
```bash
# Shell script 내용
export TF_CONFIG='{"cluster":{"worker":[...]},"task":{...}}'
```

**TrainJob command**:
```bash
source /shared/generate_tf_config.sh  # TF_CONFIG 생성
python3 /workspace/scripts/train.py   # 사용자 코드 실행
```

**중요**: TensorFlow는 추가로 `PET_NNODES` 환경변수가 필요합니다.
```yaml
trainer:
  env:
    - name: PET_NNODES
      value: "2"  # numNodes와 동일하게 설정
```

---

## API 요청 예시

### 학습 작업 생성

**Request**:
```json
POST /api/trainjob/create
{
  "user_id": "user123",
  "namespace": "user-123",
  "framework": "pytorch",
  "training_code": "import torch\nimport torch.nn as nn\n...",
  "config": {
    "num_nodes": 2,
    "gpu_per_node": 1,
    "cpu_per_node": 4,
    "memory_per_node": "16Gi"
  }
}
```

**Backend 처리 순서**:
1. ✅ System ConfigMap 생성 (`pytorch-pet-setup`)
2. ✅ User ConfigMap 생성 (`user123-train-script`)
3. ✅ TrainJob 생성 (`user123-job-20251105130000`)

**Response**:
```json
{
  "status": "success",
  "trainjob_name": "user123-job-20251105130000",
  "namespace": "user-123",
  "created_at": "2025-11-05T13:00:00Z"
}
```

### 학습 작업 상태 조회

**Request**:
```
GET /api/trainjob/{trainjob_name}/status?namespace={namespace}
```

**Response**:
```json
{
  "trainjob_name": "user123-job-20251105130000",
  "state": "Complete",  // Running, Complete, Failed
  "message": "jobset completed successfully",
  "created_at": "2025-11-05T13:00:00Z",
  "completed_at": "2025-11-05T13:05:00Z"
}
```

**상태 종류**:
- `Running`: 학습 진행 중
- `Complete`: 학습 완료
- `Failed`: 학습 실패

### 학습 로그 조회

**Request**:
```
GET /api/trainjob/{trainjob_name}/logs?namespace={namespace}&worker=0
```

**Pod 이름 형식**:
```
{trainjob_name}-node-0-{worker_index}-{random_hash}

예시:
- user123-job-20251105130000-node-0-0-abc123  # Worker 0
- user123-job-20251105130000-node-0-1-def456  # Worker 1
```

**Response**:
```json
{
  "trainjob_name": "user123-job-20251105130000",
  "worker": 0,
  "logs": "PyTorch version: 2.2.2\n✅ 분산 학습 초기화 성공!\nEpoch 1/3...\n"
}
```

### 학습 작업 삭제

**Request**:
```
DELETE /api/trainjob/{trainjob_name}?namespace={namespace}
```

**Backend 처리**:
1. TrainJob 삭제 → Pod 자동 삭제
2. User ConfigMap 삭제 (선택)
3. System ConfigMap 유지 (다른 작업이 사용 중일 수 있음)

---

## 배포 및 테스트

### 1. Runtime 설치 (관리자 - 1회만)

```bash
# PyTorch Runtime
kubectl apply -f pytorch/pytorch-runtime-simple.yaml

# TensorFlow Runtime
kubectl apply -f tensorflow/tensorflow-runtime.yaml

# 확인
kubectl get clustertrainingruntimes
```

**결과**:
```
NAME                   AGE
pytorch-simple         1m
tensorflow-distributed 1m
```

### 2. 테스트용 네임스페이스 생성

```bash
kubectl create namespace test-user
```

### 3. PyTorch 테스트

```bash
# 1. System ConfigMap 생성
kubectl apply -f pytorch/pytorch-pet-setup.yaml -n test-user

# 2. User ConfigMap 생성 (예시)
kubectl apply -f pytorch/pytorch-train-script-configmap.yaml -n test-user

# 3. TrainJob 생성
kubectl apply -f pytorch/pytorch-distributed-with-configmap.yaml -n test-user

# 4. 상태 확인
kubectl get trainjob -n test-user
kubectl get pods -n test-user

# 5. 로그 확인
kubectl logs pytorch-distributed-configmap-node-0-0-<hash> -n test-user
```

**성공 로그**:
```
🔧 PyTorch 분산 학습 환경 설정 시작
✅ PyTorch 환경변수 설정 완료!
  - RANK: 0
  - WORLD_SIZE: 2
🎉 분산 학습 초기화 성공!
Epoch 1/3...
🎉 PyTorch 분산 학습 완료!
총 노드 수: 2
최종 평균 Loss: 0.0349
```

### 4. TensorFlow 테스트

```bash
# 1. System ConfigMap 생성
kubectl apply -f tensorflow/tensorflow-tf-config-generator.yaml -n test-user

# 2. User ConfigMap 생성 (예시)
kubectl apply -f tensorflow/tensorflow-train-script-configmap.yaml -n test-user

# 3. TrainJob 생성
kubectl apply -f tensorflow/tensorflow-distributed-with-configmap.yaml -n test-user

# 4. 상태 확인
kubectl get trainjob -n test-user
kubectl get pods -n test-user

# 5. 로그 확인
kubectl logs tensorflow-distributed-configmap-node-0-0-<hash> -n test-user
```

**성공 로그**:
```
🔧 TF_CONFIG 생성 시작
✅ TF_CONFIG 생성 완료!
✅ Worker 0 initialized with 2 replicas
Epoch 1/3...
🎉 TensorFlow 분산 학습 완료!
총 노드 수: 2
최종 Accuracy: 0.9889
```

### 5. 정리

```bash
# TrainJob 삭제 (Pod도 자동 삭제)
kubectl delete trainjob --all -n test-user

# ConfigMap 삭제
kubectl delete configmap --all -n test-user

# 네임스페이스 삭제
kubectl delete namespace test-user
```

---

## 중요 참고사항

### 1. RBAC 권한

Backend Service Account에 다음 권한 필요:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: trainjob-backend-role
rules:
  - apiGroups: [""]
    resources: ["configmaps", "pods", "pods/log"]
    verbs: ["create", "get", "list", "update", "patch", "delete"]
  - apiGroups: ["trainer.kubeflow.org"]
    resources: ["trainjobs"]
    verbs: ["create", "get", "list", "update", "patch", "delete", "watch"]
```

### 2. System ConfigMap은 Idempotent

- 같은 사용자가 여러 TrainJob 생성 가능
- System ConfigMap은 처음 한 번만 생성
- 이미 존재하면 생성 skip (에러 무시)

### 3. 네임스페이스 격리

각 사용자 네임스페이스는 완전히 독립적:
- ConfigMap이 겹치지 않음
- 다른 사용자에게 영향 없음

### 4. 리소스 정리

**TrainJob 삭제 시**:
- ✅ TrainJob 삭제 → Pod 자동 삭제
- ⚠️ User ConfigMap 삭제 (선택적)
- ❌ System ConfigMap 유지 (재사용)

### 5. GPU 리소스

GPU 사용 시 다음 설정 필요:
```yaml
resourcesPerNode:
  limits:
    nvidia.com/gpu: "1"  # GPU 개수
  requests:
    nvidia.com/gpu: "1"
```

GPU 없이 CPU만 사용:
```yaml
resourcesPerNode:
  limits:
    cpu: "4"
    memory: "8Gi"
  requests:
    cpu: "2"
    memory: "4Gi"
```

---

## 문의

구현 중 문제가 발생하거나 질문이 있으면 ML 팀에 문의하세요.

**테스트 완료**:
- ✅ PyTorch 분산 학습 (2 노드, GPU)
- ✅ TensorFlow 분산 학습 (2 노드, GPU)
- ✅ 멀티테넌트 격리 확인
