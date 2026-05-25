# Base Image
FROM python:3.10-slim-bookworm

# 1. CÀI ĐẶT JAVA VÀ CÔNG CỤ
RUN apt-get update && \
    apt-get install -y openjdk-17-jre-headless procps curl && \
    rm -rf /var/lib/apt/lists/*

# 2. THIẾT LẬP JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$JAVA_HOME/bin:$PATH

# 3. CÀI ĐẶT PYSPARK & THƯ VIỆN
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- TẢI JARS (QUAN TRỌNG: PHẢI CÓ HADOOP-AWS) ---
# Spark 3.4.1 đi kèm Hadoop 3.3.4 -> Cần hadoop-aws 3.3.4 và aws-java-sdk-bundle 1.12.262

# Tạo thư mục jars (đề phòng chưa có)
RUN mkdir -p /usr/local/lib/python3.10/site-packages/pyspark/jars

# 1. Kafka Spark Connector
RUN curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/spark-sql-kafka-0-10_2.12-3.4.1.jar https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.4.1/spark-sql-kafka-0-10_2.12-3.4.1.jar && \
    curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/spark-token-provider-kafka-0-10_2.12-3.4.1.jar https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.4.1/spark-token-provider-kafka-0-10_2.12-3.4.1.jar && \
    curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/kafka-clients-3.3.2.jar https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.3.2/kafka-clients-3.3.2.jar && \
    curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/commons-pool2-2.11.1.jar https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar

# 2. MINIO / S3 SUPPORT (BẠN ĐANG THIẾU CÁI NÀY) <--- LỖI NẰM Ở ĐÂY
RUN curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/hadoop-aws-3.3.4.jar https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar && \
    curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/aws-java-sdk-bundle-1.12.262.jar https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar

# 3. ElasticSearch (Giữ nguyên nếu cần)
RUN curl -fL -o /usr/local/lib/python3.10/site-packages/pyspark/jars/elasticsearch-spark-30_2.12-8.13.4.jar https://repo1.maven.org/maven2/org/elasticsearch/elasticsearch-spark-30_2.12/8.13.4/elasticsearch-spark-30_2.12-8.13.4.jar

# 4. COPY CODE
COPY main.py .

# 5. ENTRYPOINT
CMD ["python3", "main.py"]