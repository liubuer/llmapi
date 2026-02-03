"""
API测试
"""
import pytest
import httpx
from fastapi.testclient import TestClient

# 注意：这些测试需要API服务运行中
API_BASE_URL = "http://localhost:8000"


class TestHealthEndpoints:
    """健康检查端点测试"""
    
    def test_health_check(self):
        """测试健康检查端点"""
        with httpx.Client() as client:
            response = client.get(f"{API_BASE_URL}/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "browser_sessions" in data
    
    def test_root_endpoint(self):
        """测试根路径"""
        with httpx.Client() as client:
            response = client.get(f"{API_BASE_URL}/")
            assert response.status_code == 200
            data = response.json()
            assert "name" in data
            assert "version" in data


class TestModelsEndpoints:
    """模型端点测试"""
    
    def test_list_models(self):
        """测试模型列表"""
        with httpx.Client() as client:
            response = client.get(f"{API_BASE_URL}/v1/models")
            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert len(data["data"]) > 0
    
    def test_get_model(self):
        """测试获取模型信息"""
        with httpx.Client() as client:
            response = client.get(f"{API_BASE_URL}/v1/models/gpt-5")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "gpt-5"
    
    def test_get_nonexistent_model(self):
        """测试获取不存在的模型"""
        with httpx.Client() as client:
            response = client.get(f"{API_BASE_URL}/v1/models/nonexistent")
            assert response.status_code == 404


class TestChatCompletions:
    """聊天补全测试"""
    
    @pytest.mark.slow
    def test_basic_chat(self):
        """测试基础聊天"""
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{API_BASE_URL}/v1/chat/completions",
                json={
                    "model": "gpt-5",
                    "messages": [
                        {"role": "user", "content": "说'你好'"}
                    ]
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert "message" in data["choices"][0]
    
    @pytest.mark.slow
    def test_chat_with_system_message(self):
        """测试带系统消息的聊天"""
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{API_BASE_URL}/v1/chat/completions",
                json={
                    "model": "gpt-5",
                    "messages": [
                        {"role": "system", "content": "你是一个简洁的助手，只用一个词回答。"},
                        {"role": "user", "content": "天空是什么颜色的？"}
                    ]
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
    
    def test_invalid_request(self):
        """测试无效请求"""
        with httpx.Client() as client:
            response = client.post(
                f"{API_BASE_URL}/v1/chat/completions",
                json={
                    "model": "gpt-5",
                    # 缺少messages字段
                }
            )
            assert response.status_code == 422  # Validation Error


class TestStreamingChat:
    """流式聊天测试"""
    
    @pytest.mark.slow
    def test_streaming_chat(self):
        """测试流式聊天"""
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{API_BASE_URL}/v1/chat/completions",
                json={
                    "model": "gpt-5",
                    "messages": [
                        {"role": "user", "content": "数到5"}
                    ],
                    "stream": True
                }
            ) as response:
                assert response.status_code == 200
                
                chunks = []
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        chunks.append(line)
                
                # 应该有多个数据块
                assert len(chunks) > 1
                # 最后应该是[DONE]
                assert chunks[-1] == "data: [DONE]"


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])
