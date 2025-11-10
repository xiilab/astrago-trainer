# Astrago Trainer

Kubeflow를 기반으로 하는 분산 머신러닝 학습 환경 설정 및 관리 프로젝트입니다.

## 프로젝트 개요

이 프로젝트는 PyTorch와 TensorFlow를 사용한 분산 학습 워크플로우를 Kubernetes 클러스터에서 실행하기 위한 구성 파일과 학습 스크립트를 제공합니다.

### 지원하는 프레임워크

- **PyTorch**: 2.2.2 (CUDA 11.8)
- **TensorFlow**: 2.15.0 (GPU)

## 프로젝트 구조

```
astrago-trainer/
├── README.md                        # 이 파일
├── .gitignore                       # Git 제외 파일 설정
│
├── docs/                            # 문서 및 UI 목업
│   ├── backend-guide.md             # 백엔드 구성 가이드
│   └── ui-mockups/                  # UI 디자인 목업
│       ├── index.html
│       ├── horovod.svg
│       └── training-operator.svg
│
├── runtimes/                        # 프레임워크별 런타임 및 학습 정의
│   ├── pytorch/
│   │   ├── runtime.yaml             # PyTorch ClusterTrainingRuntime 정의
│   │   ├── trainjob.yaml            # PyTorch TrainJob 예제
│   │   └── train.py                 # PyTorch 학습 스크립트
│   │
│   └── tensorflow/
│       ├── runtime.yaml             # TensorFlow ClusterTrainingRuntime 정의
│       ├── trainjob.yaml            # TensorFlow TrainJob 예제
│       └── train.py                 # TensorFlow 학습 스크립트
│
└── scripts/                         # 유틸리티 스크립트
    └── merge_preview.py             # 병합 미리보기 도구

```

## 빠른 시작

### 1. 사전 요구사항

- Kubernetes 클러스터
- Kubeflow Training Operator 설치
- kubectl CLI 설정 완료

### 2. PyTorch 분산 학습 실행

```bash
# TrainJob 생성
kubectl apply -f runtimes/pytorch/runtime.yaml
kubectl apply -f runtimes/pytorch/trainjob.yaml

# 상태 확인
kubectl get trainjob -n kubeflow-system
kubectl logs -n kubeflow-system <pod-name> -c node
```

### 3. TensorFlow 분산 학습 실행

```bash
# TrainJob 생성
kubectl apply -f runtimes/tensorflow/runtime.yaml
kubectl apply -f runtimes/tensorflow/trainjob.yaml

# 상태 확인
kubectl get trainjob -n kubeflow-system
kubectl logs -n kubeflow-system <pod-name> -c node
```

## 주요 기능

### 런타임 (Runtime)

- **ClusterTrainingRuntime**: Kubeflow Training Operator의 커스텀 리소스
- 프레임워크별 기본 설정 (이미지, 리소스, 환경변수)
- TTL 설정으로 완료된 작업 자동 정리 (`ttlSecondsAfterFinished: 86400`)

### 학습 작업 (TrainJob)

- **분산 학습 설정**: 다중 노드 지원
- **Git 저장소 자동 연동**: 최신 학습 코드를 Git에서 가져옴
- **환경 변수 관리**: 프레임워크별 설정 자동 생성
- **리소스 제한**: CPU, 메모리, GPU 할당 설정

### 학습 스크립트

- PyTorch: 분산 데이터 병렬(DDP) 학습 지원
- TensorFlow: TF_CONFIG를 활용한 분산 학습 지원

## 설정 요소

### TrainJob 주요 설정

```yaml
spec:
  numNodes: 2                    # 학습 노드 수
  runtimeRef:
    name: pytorch-runtime       # 사용할 Runtime 참조
  trainer:
    image: pytorch/pytorch:...  # Docker 이미지
    resourcesPerNode:           # 노드당 리소스
      limits:
        cpu: "4"
        memory: "16Gi"
        nvidia.com/gpu: "1"
```

### Git 연동 설정

학습 코드는 자동으로 Git 저장소에서 가져옵니다:

```yaml
initContainers:
  - name: git-clone
    env:
      - name: GIT_SYNC_REPO
        value: https://github.com/xiilab/astrago-trainer.git
      - name: GIT_SYNC_BRANCH
        value: main
```

## 사용 사례

### 1. PyTorch 분산 학습

PyTorch DDP (Distributed Data Parallel)를 사용한 분산 학습:

- 여러 노드에서 데이터를 병렬로 처리
- 노드 간 통신을 통한 그래디언트 동기화
- `RANK`, `WORLD_SIZE`, `MASTER_ADDR` 환경변수 자동 설정

### 2. TensorFlow 분산 학습

TensorFlow의 분산 전략을 사용한 학습:

- `TF_CONFIG` 환경변수를 통한 클러스터 구성
- 다중 워커(Worker) 설정 지원
- 자동 포트 할당 및 서비스 디스커버리

## 문서

자세한 구성 및 커스터마이징 정보는 [docs/backend-guide.md](docs/backend-guide.md)를 참조하세요.

## 주요 변경사항

- **v1.1**: 디렉토리 구조 최적화 및 문서 개선
  - Runtime 및 TrainJob 파일 표준화
  - 레거시 ConfigMap 제거
  - 프로젝트 구조 정리

## 라이선스

이 프로젝트는 Kubeflow 및 관련 오픈소스 프로젝트와 함께 사용됩니다.

## 문의

문제나 제안사항이 있으면 GitHub Issues를 통해 보고해주세요.
