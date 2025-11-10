# UI Mockups — 분산 학습 설정

이 폴더에는 Horovod(MPI Operator)와 TensorFlow/PyTorch(Training Operator) 전환을 반영한 목업이 포함되어 있습니다.

## 파일 구성
- `index.html`: 브라우저에서 바로 열어볼 수 있는 인터랙티브 목업. 상단의 "분산 학습 타입" 셀렉트로 Horovod UI와 Training Operator UI를 전환합니다.
- `horovod.svg`: 기존 Horovod(MPI Operator) UI의 정적 이미지 목업.
- `training-operator.svg`: TensorFlow/PyTorch용 Training Operator UI의 정적 이미지 목업.

## 사용 방법
1. 로컬에서 `index.html` 파일을 더블클릭하여 브라우저로 엽니다.
2. 상단의 "분산 학습 타입"에서 아래 중 하나를 선택합니다.
   - TensorFlow (Training Operator)
   - PyTorch (Training Operator)
   - Horovod (MPI Operator)
3. Horovod 선택 시 기존 UI(Launcher/Worker 분리)가 그대로 노출됩니다.
4. TensorFlow/PyTorch 선택 시 Training Operator 규칙에 맞게 `노드 개수(Replicas)`만 지정하고 리소스는 Worker 단일 섹션에서 설정하도록 단순화됩니다.

## 비고
- 본 목업은 기능 연동 없이 UI 배치를 확인하기 위한 용도입니다.
- 실제 연동 시 이미지 프리셋, 자원 프리셋, GPU/CPU/MEM 값은 백엔드 스펙에 맞춰 바인딩하면 됩니다.


