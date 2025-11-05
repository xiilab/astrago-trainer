# Kubeflow Training Operator v2 - Backend 개발 가이드

백엔드 개발자를 위한 TrainJob 생성 가이드입니다.
**UI에서 받은 값들을 TrainJob YAML의 어디에 넣어야 하는지** 명확하게 설명합니다.

---

## 📋 목차
- [UI 입력 → TrainJob 매핑](#ui-입력--trainjob-매핑)
- [Backend 구현 가이드](#backend-구현-가이드)
- [프레임워크별 차이점](#프레임워크별-차이점)
- [배포 및 테스트](#배포-및-테스트)

---

## UI 입력 → TrainJob 매핑

사용자가 UI에서 입력하는 값들과 TrainJob YAML 필드의 매핑 관계입니다.

### 📥 UI 입력 항목

| UI 항목 | 설명 | 예시 값 |
|---------|------|---------|
| **이미지 주소** | 학습에 사용할 Docker 이미지 | `pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime` |
| **CPU** | 컨테이너당 CPU 요청/제한 | `2` / `4` |
| **MEMORY** | 컨테이너당 메모리 요청/제한 | `8Gi` / `16Gi` |
| **GPU** | 컨테이너당 GPU 개수 | `1` |
| **분산학습 노드 개수** | 학습에 사용할 노드(워커) 수 | `2` |
| **볼륨 마운트** | 소스코드, 데이터셋, 모델 저장소 | `[{"name": "code", "path": "/workspace"}, ...]` |
| **커맨드** | 컨테이너 실행 명령 | `python /workspace/scripts/train.py` |
| **환경변수** | 사용자 정의 환경변수 | `[{"name": "EPOCHS", "value": "10"}, ...]` |

---

### 🎯 TrainJob YAML 매핑

#### **PyTorch TrainJob 예시**

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: user-job-12345                    # Backend가 생성 (user_id + timestamp)
  namespace: user-namespace               # 사용자 네임스페이스
spec:
  runtimeRef:
    name: pytorch-simple                  # 고정값 (PyTorch Runtime 이름)

  trainer:
    # ============================================================
    # UI 입력: 이미지 주소
    # ============================================================
    image: pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime

    # ============================================================
    # UI 입력: 분산학습 노드 개수
    # ============================================================
    numNodes: 2

    # ============================================================
    # UI 입력: 커맨드
    # ============================================================
    command:
      - bash
      - -c
      - |
        # PyTorch 환경변수 설정 (자동 추가)
        export RANK=${PET_NODE_RANK:-0}
        export LOCAL_RANK=${PET_LOCAL_RANK:-0}
        export WORLD_SIZE=${PET_NNODES:-1}
        export MASTER_ADDR=${PET_MASTER_ADDR:-localhost}
        export MASTER_PORT=${PET_MASTER_PORT:-29500}

        # 사용자 입력 커맨드 (UI에서 받음)
        python /workspace/scripts/train.py

    # ============================================================
    # UI 입력: CPU, MEMORY, GPU
    # ============================================================
    resourcesPerNode:
      limits:
        cpu: "4"                           # UI 입력: CPU 제한
        memory: "16Gi"                     # UI 입력: MEMORY 제한
        nvidia.com/gpu: "1"                # UI 입력: GPU 개수
      requests:
        cpu: "2"                           # UI 입력: CPU 요청
        memory: "8Gi"                      # UI 입력: MEMORY 요청
        nvidia.com/gpu: "1"                # GPU는 requests = limits

  # ============================================================
  # UI 입력: 볼륨 마운트
  # ============================================================
  podTemplateOverrides:
    - targetJobs:
        - name: node
      spec:
        volumes:
          # 소스코드 볼륨
          - name: train-script
            configMap:
              name: user-train-script      # Backend가 생성한 ConfigMap 이름
              defaultMode: 0755

          # 데이터셋 볼륨 (예시: PVC)
          - name: dataset
            persistentVolumeClaim:
              claimName: user-dataset-pvc

          # 모델 저장소 볼륨 (예시: PVC)
          - name: models
            persistentVolumeClaim:
              claimName: user-models-pvc

        containers:
          - name: node
            # ============================================================
            # UI 입력: 환경변수
            # ============================================================
            env:
              - name: EPOCHS                # 사용자 정의 환경변수
                value: "10"
              - name: BATCH_SIZE
                value: "64"
              - name: LEARNING_RATE
                value: "0.001"

            volumeMounts:
              - name: train-script
                mountPath: /workspace/scripts
                readOnly: true
              - name: dataset
                mountPath: /data
                readOnly: true
              - name: models
                mountPath: /models
                readOnly: false
```

---

#### **TensorFlow TrainJob 예시**

```yaml
apiVersion: trainer.kubeflow.org/v1alpha1
kind: TrainJob
metadata:
  name: user-job-12345
  namespace: user-namespace
spec:
  runtimeRef:
    name: tensorflow-distributed           # 고정값 (TensorFlow Runtime 이름)

  trainer:
    # UI 입력: 이미지 주소
    image: tensorflow/tensorflow:2.15.0-gpu

    # UI 입력: 분산학습 노드 개수
    numNodes: 2

    # UI 입력: 커맨드
    command:
      - bash
      - -c
      - |
        # TF_CONFIG 로드 (자동 추가)
        source /shared-env/tf_config.env
        echo "TF_CONFIG: $TF_CONFIG"

        # 사용자 입력 커맨드
        python3 /workspace/scripts/train.py

    # UI 입력: CPU, MEMORY, GPU
    resourcesPerNode:
      limits:
        cpu: "4"
        memory: "16Gi"
        nvidia.com/gpu: "1"
      requests:
        cpu: "2"
        memory: "8Gi"
        nvidia.com/gpu: "1"

  # UI 입력: 볼륨 마운트
  podTemplateOverrides:
    - targetJobs:
        - name: node
      spec:
        volumes:
          - name: train-script
            configMap:
              name: user-train-script
              defaultMode: 0755
          - name: dataset
            persistentVolumeClaim:
              claimName: user-dataset-pvc
          - name: models
            persistentVolumeClaim:
              claimName: user-models-pvc

        # ⚠️ TensorFlow 전용: initContainer에 PET_NNODES 설정 필요
        initContainers:
          - name: tf-config-generator
            env:
              - name: PET_NNODES
                value: "2"                 # numNodes와 동일하게 설정

        containers:
          - name: node
            # UI 입력: 환경변수
            env:
              - name: EPOCHS
                value: "10"
              - name: BATCH_SIZE
                value: "64"

            volumeMounts:
              - name: train-script
                mountPath: /workspace/scripts
                readOnly: true
              - name: dataset
                mountPath: /data
                readOnly: true
              - name: models
                mountPath: /models
                readOnly: false
```

---

## Backend 구현 가이드

### 🔧 전체 처리 흐름

```
UI 요청
  ↓
Backend API
  ↓
1. User ConfigMap 생성 (사용자 소스코드)
2. TrainJob YAML 생성 (위 템플릿 + UI 입력값)
3. TrainJob 배포
  ↓
Kubernetes
  ↓
Pod 생성 및 학습 실행
```

---

### 📝 구현 예시 (Python)

#### **1단계: User ConfigMap 생성**

```python
def create_user_configmap(user_id: str, namespace: str, training_code: str) -> str:
    """
    사용자 학습 코드를 ConfigMap으로 생성

    Returns:
        ConfigMap 이름
    """
    configmap_name = f"{user_id}-train-script"

    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": configmap_name,
            "namespace": namespace
        },
        "data": {
            "train.py": training_code  # UI에서 받은 Python 코드
        }
    }

    # Kubernetes API로 생성
    k8s_core_v1.create_namespaced_config_map(
        namespace=namespace,
        body=configmap
    )

    return configmap_name
```

---

#### **2단계: TrainJob 생성 함수**

```python
def create_trainjob(
    user_id: str,
    namespace: str,
    framework: str,  # "pytorch" 또는 "tensorflow"
    image: str,
    num_nodes: int,
    cpu_request: str,
    cpu_limit: str,
    memory_request: str,
    memory_limit: str,
    gpu_count: int,
    command: str,
    env_vars: List[Dict[str, str]],
    volumes: List[Dict[str, Any]],
    configmap_name: str
) -> str:
    """
    TrainJob YAML 생성 및 배포

    Args:
        user_id: 사용자 ID
        namespace: 사용자 네임스페이스
        framework: "pytorch" 또는 "tensorflow"
        image: Docker 이미지 주소
        num_nodes: 분산학습 노드 개수
        cpu_request/cpu_limit: CPU 리소스
        memory_request/memory_limit: 메모리 리소스
        gpu_count: GPU 개수
        command: 사용자 실행 명령
        env_vars: [{"name": "KEY", "value": "VALUE"}, ...]
        volumes: [{"name": "vol1", "pvc": "pvc-name", "mountPath": "/data"}, ...]
        configmap_name: 학습 코드 ConfigMap 이름

    Returns:
        TrainJob 이름
    """
    import time
    trainjob_name = f"{user_id}-job-{int(time.time())}"

    # Runtime 이름 결정
    runtime_name = "pytorch-simple" if framework == "pytorch" else "tensorflow-distributed"

    # 프레임워크별 환경변수 설정 스크립트 생성
    if framework == "pytorch":
        env_setup = """
        export RANK=${PET_NODE_RANK:-0}
        export LOCAL_RANK=${PET_LOCAL_RANK:-0}
        export WORLD_SIZE=${PET_NNODES:-1}
        export MASTER_ADDR=${PET_MASTER_ADDR:-localhost}
        export MASTER_PORT=${PET_MASTER_PORT:-29500}
        """
    else:  # tensorflow
        env_setup = """
        source /shared-env/tf_config.env
        echo "TF_CONFIG: $TF_CONFIG"
        """

    # 전체 커맨드 조합
    full_command = f"""
{env_setup}

# 사용자 커맨드
{command}
"""

    # 볼륨 및 볼륨 마운트 생성
    volume_specs = []
    volume_mounts = []

    # 소스코드 볼륨 (필수)
    volume_specs.append({
        "name": "train-script",
        "configMap": {
            "name": configmap_name,
            "defaultMode": 0o755
        }
    })
    volume_mounts.append({
        "name": "train-script",
        "mountPath": "/workspace/scripts",
        "readOnly": True
    })

    # 사용자 정의 볼륨 추가
    for vol in volumes:
        volume_specs.append({
            "name": vol["name"],
            "persistentVolumeClaim": {
                "claimName": vol["pvc"]
            }
        })
        volume_mounts.append({
            "name": vol["name"],
            "mountPath": vol["mountPath"],
            "readOnly": vol.get("readOnly", False)
        })

    # TrainJob 생성
    trainjob = {
        "apiVersion": "trainer.kubeflow.org/v1alpha1",
        "kind": "TrainJob",
        "metadata": {
            "name": trainjob_name,
            "namespace": namespace
        },
        "spec": {
            "runtimeRef": {
                "name": runtime_name
            },
            "trainer": {
                "image": image,
                "numNodes": num_nodes,
                "command": ["bash", "-c", full_command],
                "resourcesPerNode": {
                    "limits": {
                        "cpu": cpu_limit,
                        "memory": memory_limit,
                        "nvidia.com/gpu": str(gpu_count)
                    },
                    "requests": {
                        "cpu": cpu_request,
                        "memory": memory_request,
                        "nvidia.com/gpu": str(gpu_count)
                    }
                }
            },
            "podTemplateOverrides": [
                {
                    "targetJobs": [{"name": "node"}],
                    "spec": {
                        "volumes": volume_specs,
                        "containers": [
                            {
                                "name": "node",
                                "env": env_vars,
                                "volumeMounts": volume_mounts
                            }
                        ]
                    }
                }
            ]
        }
    }

    # ⚠️ TensorFlow 전용: initContainer에 PET_NNODES 설정
    if framework == "tensorflow":
        trainjob["spec"]["podTemplateOverrides"][0]["spec"]["initContainers"] = [
            {
                "name": "tf-config-generator",
                "env": [
                    {
                        "name": "PET_NNODES",
                        "value": str(num_nodes)
                    }
                ]
            }
        ]

    # Kubernetes API로 배포
    k8s_custom.create_namespaced_custom_object(
        group="trainer.kubeflow.org",
        version="v1alpha1",
        namespace=namespace,
        plural="trainjobs",
        body=trainjob
    )

    return trainjob_name
```

---

#### **3단계: API 엔드포인트 예시**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

router = APIRouter()

class VolumeMount(BaseModel):
    name: str
    pvc: str
    mountPath: str
    readOnly: bool = False

class TrainJobRequest(BaseModel):
    user_id: str
    namespace: str
    framework: str  # "pytorch" or "tensorflow"
    training_code: str
    image: str
    num_nodes: int
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str
    gpu_count: int
    command: str
    env_vars: List[Dict[str, str]] = []
    volumes: List[VolumeMount] = []

@router.post("/trainjob/create")
async def create_training_job(request: TrainJobRequest):
    """
    학습 작업 생성 API
    """
    try:
        # 1. User ConfigMap 생성
        configmap_name = create_user_configmap(
            user_id=request.user_id,
            namespace=request.namespace,
            training_code=request.training_code
        )

        # 2. TrainJob 생성
        trainjob_name = create_trainjob(
            user_id=request.user_id,
            namespace=request.namespace,
            framework=request.framework,
            image=request.image,
            num_nodes=request.num_nodes,
            cpu_request=request.cpu_request,
            cpu_limit=request.cpu_limit,
            memory_request=request.memory_request,
            memory_limit=request.memory_limit,
            gpu_count=request.gpu_count,
            command=request.command,
            env_vars=request.env_vars,
            volumes=[vol.dict() for vol in request.volumes],
            configmap_name=configmap_name
        )

        return {
            "status": "success",
            "trainjob_name": trainjob_name,
            "namespace": request.namespace
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

#### **4단계: API 요청 예시**

```bash
curl -X POST http://localhost:8000/api/trainjob/create \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "namespace": "user-123",
    "framework": "pytorch",
    "training_code": "import torch\nimport torch.nn as nn\nprint(\"Training...\")",
    "image": "pytorch/pytorch:2.2.2-cuda11.8-cudnn8-runtime",
    "num_nodes": 2,
    "cpu_request": "2",
    "cpu_limit": "4",
    "memory_request": "8Gi",
    "memory_limit": "16Gi",
    "gpu_count": 1,
    "command": "python /workspace/scripts/train.py",
    "env_vars": [
      {"name": "EPOCHS", "value": "10"},
      {"name": "BATCH_SIZE", "value": "64"}
    ],
    "volumes": [
      {
        "name": "dataset",
        "pvc": "user123-dataset-pvc",
        "mountPath": "/data",
        "readOnly": true
      },
      {
        "name": "models",
        "pvc": "user123-models-pvc",
        "mountPath": "/models",
        "readOnly": false
      }
    ]
  }'
```

---

## 프레임워크별 차이점

### PyTorch

**환경변수 설정 (자동 추가)**:
```bash
export RANK=${PET_NODE_RANK:-0}
export LOCAL_RANK=${PET_LOCAL_RANK:-0}
export WORLD_SIZE=${PET_NNODES:-1}
export MASTER_ADDR=${PET_MASTER_ADDR:-localhost}
export MASTER_PORT=${PET_MASTER_PORT:-29500}
```

**Runtime 이름**: `pytorch-simple`

---

### TensorFlow

**환경변수 설정 (자동 추가)**:
```bash
source /shared-env/tf_config.env
echo "TF_CONFIG: $TF_CONFIG"
```

**Runtime 이름**: `tensorflow-distributed`

**⚠️ 추가 필요 사항**:
- `initContainers`에 `PET_NNODES` 환경변수 설정 필수
- `PET_NNODES` 값은 `trainer.numNodes`와 동일하게 설정

```yaml
initContainers:
  - name: tf-config-generator
    env:
      - name: PET_NNODES
        value: "2"  # numNodes와 동일
```

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

---

### 2. 테스트용 네임스페이스 생성

```bash
kubectl create namespace test-user
```

---

### 3. PyTorch 테스트

```bash
# User ConfigMap 생성 (예시)
kubectl apply -f pytorch/pytorch-train-script-configmap.yaml -n test-user

# TrainJob 생성
kubectl apply -f pytorch/pytorch-distributed-with-configmap.yaml -n test-user

# 상태 확인
kubectl get trainjob -n test-user
kubectl get pods -n test-user | grep pytorch

# 로그 확인
kubectl logs <pod-name> -n test-user
```

**성공 로그**:
```
🎉 분산 학습 초기화 성공!
  - Rank: 0/2
  - World Size: 2
  - Device: cuda:0
🚀 분산 학습 시작 (총 2개 노드)
Epoch 1, Batch 0/469, Loss: 2.3085
...
🎉 PyTorch 분산 학습 완료!
총 노드 수: 2
최종 평균 Loss: 0.0367
```

---

### 4. TensorFlow 테스트

```bash
# User ConfigMap 생성 (예시)
kubectl apply -f tensorflow/tensorflow-train-script-configmap.yaml -n test-user

# TrainJob 생성
kubectl apply -f tensorflow/tensorflow-distributed-with-configmap.yaml -n test-user

# 상태 확인
kubectl get trainjob -n test-user
kubectl get pods -n test-user | grep tensorflow

# 로그 확인
kubectl logs <pod-name> -n test-user -c node
```

**성공 로그**:
```
✅ TF_CONFIG 로드 완료: Worker 0
✅ Worker 0 initialized with 2 replicas
🚀 분산 학습 시작 (총 2개 워커)
Epoch 1/3...
🎉 TensorFlow 분산 학습 완료!
총 노드 수: 2
최종 Accuracy: 0.9884
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

---

### 2. GPU 리소스 설정

**GPU 사용**:
```yaml
resourcesPerNode:
  limits:
    nvidia.com/gpu: "1"
  requests:
    nvidia.com/gpu: "1"  # GPU는 requests = limits 동일하게
```

**GPU 없이 CPU만**:
```yaml
resourcesPerNode:
  limits:
    cpu: "4"
    memory: "16Gi"
  requests:
    cpu: "2"
    memory: "8Gi"
  # nvidia.com/gpu 필드 제거
```

---

### 3. 볼륨 마운트 타입

**ConfigMap**:
```yaml
- name: train-script
  configMap:
    name: user-train-script
    defaultMode: 0755
```

**PVC (PersistentVolumeClaim)**:
```yaml
- name: dataset
  persistentVolumeClaim:
    claimName: user-dataset-pvc
```

**hostPath (테스트용만)**:
```yaml
- name: local-data
  hostPath:
    path: /data
    type: Directory
```

---

### 4. 리소스 정리

**TrainJob 삭제**:
```bash
kubectl delete trainjob <trainjob-name> -n <namespace>
```
→ Pod 자동 삭제됨

**ConfigMap 삭제**:
```bash
kubectl delete configmap <configmap-name> -n <namespace>
```

---

## 문의

구현 중 문제가 발생하거나 질문이 있으면 ML 팀에 문의하세요.

**테스트 완료**:
- ✅ PyTorch 분산 학습 (2 노드, GPU)
- ✅ TensorFlow 분산 학습 (2 노드, GPU)
- ✅ 멀티 볼륨 마운트 (소스코드, 데이터셋, 모델)
- ✅ 사용자 정의 환경변수
