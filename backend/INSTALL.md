# MaterialHub Backend 安装说明

## 依赖安装

### 方法1：使用国内镜像源（推荐）

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

### 方法2：使用默认PyPI源

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 关键依赖

- **PyMuPDF (fitz)**: PDF文本提取和页面渲染
  - 版本: >=1.23.0
  - 用于：智能导入中的PDF处理和OCR
  
- **python-docx**: Word文档解析
- **Pillow**: 图像处理
- **FastAPI + Uvicorn**: Web框架

## 验证安装

```bash
# 验证PyMuPDF
venv/bin/python -c "import fitz; print('PyMuPDF version:', fitz.version)"

# 验证OCR服务连接
venv/bin/python -c "from ocr_client import check_ocr_service; print('OCR可用' if check_ocr_service() else 'OCR不可用')"
```

## 启动服务

```bash
venv/bin/python main.py
```

## 常见问题

### 1. PyMuPDF安装失败
```bash
# 使用国内镜像源
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple PyMuPDF
```

### 2. OCR服务不可用
检查 `.env` 文件中的 `OCR_SERVICE_URL` 配置：
- 后端直接运行在宿主机：`http://localhost:8010`
- 后端在Docker容器中：`http://host.docker.internal:8010`
