"""
TensorFlow 분산 학습 예제
TF_CONFIG는 initContainer에서 설정됨
"""
import os
import json
import tensorflow as tf


# TF_CONFIG 확인
tf_config = json.loads(os.environ.get('TF_CONFIG', '{}'))
worker_index = tf_config.get('task', {}).get('index', 0)
print(f"\n✅ TF_CONFIG 로드 완료: Worker {worker_index}")


strategy = tf.distribute.MultiWorkerMirroredStrategy()
print(f'✅ Worker {worker_index} initialized with {strategy.num_replicas_in_sync} replicas')

# MNIST 데이터셋 로드
print("📥 MNIST 데이터셋 로드 중...")
(x_train, y_train), _ = tf.keras.datasets.mnist.load_data()
x_train = x_train.reshape(-1, 28, 28, 1).astype('float32') / 255.0

batch_size = 64 * strategy.num_replicas_in_sync
train_ds = (tf.data.Dataset
            .from_tensor_slices((x_train, y_train))
            .shuffle(60000)
            .batch(batch_size)
            .repeat())

# 모델 생성 및 컴파일
with strategy.scope():
    model = tf.keras.Sequential([
        tf.keras.layers.Conv2D(32, 3, activation='relu', input_shape=(28, 28, 1)),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Conv2D(64, 3, activation='relu'),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dense(10, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

print("📦 모델 생성 완료")

# 학습 시작
num_workers = len(tf_config.get("cluster", {}).get("worker", []))
if worker_index == 0:
    print(f"🚀 분산 학습 시작 (총 {num_workers}개 워커)")

history = model.fit(train_ds, epochs=3, steps_per_epoch=60000//batch_size, verbose=1 if worker_index==0 else 0)

# 결과 출력
if worker_index == 0:
    print("="*60)
    print("🎉 TensorFlow 분산 학습 완료!")
    print("="*60)
    print(f"총 노드 수: {num_workers}")
    print(f"최종 Accuracy: {history.history['accuracy'][-1]:.4f}")
    print(f"Framework: Kubeflow Trainer v2")
    print("="*60)


