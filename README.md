# AI 旅游规划 Agent

基于 **Multi-Agent 协作架构** 的智能旅游规划系统，支持自然语言输入，多个 AI Agent 协作完成景点推荐、路线规划、酒店餐饮推荐、交通规划，最终输出完整可执行的行程单。

## 核心特性

- **Multi-Agent 协作**：LLM 驱动的动态 Supervisor 调度 8 个专职 Agent（景点/路线/酒店/餐饮/交通/编译/校验/审批）
- **RAG 语义搜索**：ChromaDB 向量库 + 高德 POI API 混合检索，中文语义匹配（bge-small-zh-v1.5）
- **用户画像记忆**：长期偏好学习（兴趣/节奏/预算/口味），历史行程复用
- **实时流式体验**：SSE 推送 Agent 进度，前端实时展示规划过程
- **Human-in-the-Loop**：行程生成后可审批、局部编辑、回溯历史版本
- **JWT 用户认证**：注册/登录，行程数据隔离，偏好个人化

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Element Plus + Leaflet |
| 后端 | FastAPI + Python 3.12 |
| Agent 编排 | LangGraph StateGraph + 动态 Supervisor |
| LLM | DeepSeek (chat + reasoner) |
| 向量库 | ChromaDB + sentence-transformers |
| 数据库 | PostgreSQL / SQLite + Redis |
| 部署 | Docker Compose + Nginx |

## 快速开始

### 前提条件

- Python 3.11+
- Node.js 20+
- Docker Desktop（可选，用于 Docker 部署）

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/travel-agent.git
cd travel-agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入你的 API Key：

```env
DEEPSEEK_API_KEY=sk-your-key
AMAP_API_KEY=your-amap-key
```

### 3. 本地开发

**后端：**

```bash
cd backend
pip install -e .
python -m scripts.seed_all all    # 导入种子数据到 ChromaDB
uvicorn app.main:app --reload     # 启动后端 http://localhost:8000
```

**前端：**

```bash
cd frontend
npm install
npm run dev                       # 启动前端 http://localhost:5173
```

### 4. Docker 一键部署

```bash
docker compose up -d
```

访问 `http://localhost` 即可使用。

## 项目结构

```
travel_agent/
├── backend/
│   ├── app/
│   │   ├── api/           # REST API + SSE + WebSocket
│   │   ├── db/            # SQLAlchemy ORM 模型
│   │   ├── graph/         # LangGraph 节点（Agent 编排）
│   │   ├── providers/     # LLM 提供商（DeepSeek）
│   │   ├── schemas/       # Pydantic 数据模型
│   │   └── services/      # 业务服务（ChromaDB/用户画像/Auth）
│   └── scripts/           # 种子数据脚本
├── frontend/
│   └── src/
│       ├── api/           # API 客户端
│       ├── components/    # Vue 组件
│       ├── stores/        # Pinia 状态管理
│       ├── types/         # TypeScript 类型
│       └── views/         # 页面组件
├── nginx.conf             # Nginx 反向代理配置
├── docker-compose.yml     # Docker 编排
└── .env.example           # 环境变量模板
```

## Agent 协作流程

```
用户输入 → parse_request → supervisor（动态调度）
                              ├─ attraction（景点推荐）
                              ├─ route（路线规划）
                              ├─ hotel（酒店推荐）
                              ├─ restaurant（餐厅推荐）
                              ├─ transport（交通规划）
                              ├─ itinerary_compiler（行程整合）
                              ├─ constraint_validator（约束校验）
                              └─ human_approval（人工审批）
```

## API 核心端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/auth/register` | 用户注册 |
| `POST` | `/api/v1/auth/login` | 用户登录 |
| `POST` | `/api/v1/trips/stream` | SSE 流式规划 |
| `GET` | `/api/v1/trips` | 历史行程列表 |
| `GET` | `/api/v1/trips/{id}` | 行程详情 |
| `PUT` | `/api/v1/trips/{id}` | 编辑行程 |
| `GET` | `/api/v1/profile` | 用户画像 |

## License

MIT
