# 知更 Robin — 生产/部署镜像
# 构建: docker build -t robin-brief .
# 演示: docker run --rm -v "${PWD}/output:/app/output" robin-brief robin demo
# 真实: docker run --rm --env-file .env -v "${PWD}/output:/app/output" -v "${PWD}/data:/app/data" robin-brief robin run

FROM python:3.12-slim

WORKDIR /app

# 先拷依赖清单利用层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目代码并安装
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir --no-deps .

# 运行期目录（挂载卷持久化）
RUN mkdir -p output data
VOLUME ["/app/output", "/app/data"]

CMD ["robin", "--help"]
