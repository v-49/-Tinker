

---

# Tinker 🚀 (Python 3.9)

### 简介 / Introduction
**Tinker** 是一个基于 Python 3.9 构建的高效应用。包含消息队列，主动推送，被动查询，支持快速部署，轻松集成 MySQL 数据库。

---

## 如何开始 / Getting Started

### 本地运行 / Local Setup

1. **修改配置文件**  
   打开 `cfg.py` 文件，在 `DATABASE_URL` 中添加你的数据库地址：
   ```python
   DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://user:password@host:port/database")
   ```

2. **运行应用**  
   在终端中输入以下命令启动应用：
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 5896
   ```

3. **检查数据库**  
   确保你的数据库表结构和字段与应用需求一致，必要时进行调整。

---

### 使用 Docker 部署 / Deploy with Docker

1. **Dockerfile 配置**
   项目使用以下 Dockerfile 进行容器化：

   ```dockerfile
   # 使用 Python 3.9 作为基础镜像
   FROM docker.1ms.run/python:3.9-slim
   WORKDIR /app

   # 将主机上的 tinker 目录复制到容器的 /app 目录
   COPY ./tinker /app

   # 安装所需的 Python 包
   RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
       pip config set global.trusted-host mirrors.aliyun.com
   RUN pip install --no-cache-dir -r requirements.txt

   # 暴露端口 5896
   EXPOSE 5896

   # 设置容器启动时运行的命令
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5896"]
   ```

2. **启动容器**  
   使用以下命令运行 Docker 容器：
   ```bash
   docker run -d \
     -p 5896:5896 \
     --name tinker \
     -e TZ=Asia/Shanghai \
     -e DATABASE_URL="mysql+pymysql://root:mysql_password@db_host:3306/my_database" \
     tinker
   ```

---

## 项目目录结构 / Project Structure

```plaintext
/app
├── cfg.py               # 配置文件
├── app
│   ├── main.py          # 应用主入口
│   ├── models           # 数据库模型
│   ├── routers          # 路由定义
│   └── utils            # 工具函数
├── requirements.txt     # Python 依赖包
├── Dockerfile           # Docker 配置
└── README.md            # 项目说明
```

---

## 环境变量 / Environment Variables

| 名称               | 描述                                   | 示例值                                         |
|--------------------|--------------------------------------|----------------------------------------------|
| `DATABASE_URL`     | 数据库连接地址                        | `mysql+pymysql://user:password@host:port/db` |
| `TZ`               | 容器时区设置                          | `Asia/Shanghai`                              |

---

## 联系我们 / Contact Us

- **作者 / Author:** 49
- **邮箱 / Email:** UN
- **GitHub:**

欢迎贡献和反馈！ / Contributions and feedback are welcome! 😊

--- 
