"""
LangChain RAG (检索增强生成) 示例

功能：
- 使用Chroma向量数据库存储文档
- 支持多种文档格式（TXT、PDF）
- 文档切分和向量化
- 基于检索的问答

依赖安装：
    pip install langchain langchain-openai langchain-community
    pip install chromadb sentence-transformers
    pip install pypdf  # PDF支持

运行前确保API服务已启动：
    start.bat api
"""
import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain.schema import Document


# ========== 1. 配置 ==========

# LLM配置 - 连接到本地API
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5",
    temperature=0
)

# Embedding模型 - 使用HuggingFace本地模型（无需外部API）
# 首次运行会自动下载模型（约500MB）
print("正在加载Embedding模型...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
print("Embedding模型加载完成!")

# 向量数据库存储路径
CHROMA_PATH = "./chroma_db"


# ========== 2. 文档处理 ==========

def load_text_file(filepath: str) -> list:
    """加载文本文件"""
    from langchain_community.document_loaders import TextLoader
    loader = TextLoader(filepath, encoding='utf-8')
    return loader.load()


def load_pdf_file(filepath: str) -> list:
    """加载PDF文件"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(filepath)
        return loader.load()
    except ImportError:
        print("请安装pypdf: pip install pypdf")
        return []


def load_directory(dir_path: str) -> list:
    """加载目录下所有文档"""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader

    documents = []

    # 加载txt文件
    txt_loader = DirectoryLoader(
        dir_path,
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={'encoding': 'utf-8'}
    )
    documents.extend(txt_loader.load())

    # 加载pdf文件
    try:
        from langchain_community.document_loaders import PyPDFLoader
        pdf_loader = DirectoryLoader(
            dir_path,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader
        )
        documents.extend(pdf_loader.load())
    except ImportError:
        print("提示：安装pypdf以支持PDF文件")

    return documents


def split_documents(documents: list, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """文档切分"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
    )
    return text_splitter.split_documents(documents)


# ========== 3. 向量数据库 ==========

def create_vectorstore(documents: list, persist_dir: str = CHROMA_PATH):
    """创建向量数据库"""
    # 切分文档
    chunks = split_documents(documents)
    print(f"文档切分完成，共 {len(chunks)} 个片段")

    # 创建向量数据库
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    print(f"向量数据库已创建: {persist_dir}")
    return vectorstore


def load_vectorstore(persist_dir: str = CHROMA_PATH):
    """加载已有的向量数据库"""
    if not os.path.exists(persist_dir):
        raise FileNotFoundError(f"向量数据库不存在: {persist_dir}")

    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings
    )


# ========== 4. RAG链 ==========

def create_qa_chain(vectorstore, k: int = 3):
    """创建问答链"""

    # 检索器
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )

    # 自定义提示模板
    prompt_template = """你是一个专业的问答助手。请根据以下提供的参考信息来回答问题。

要求：
1. 只根据提供的参考信息回答，不要编造
2. 如果参考信息中没有相关内容，请明确说明"根据已知信息无法回答"
3. 回答要准确、简洁、专业

参考信息：
{context}

问题：{question}

回答："""

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # 创建问答链
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    return qa_chain


# ========== 5. RAG应用类 ==========

class RAGApplication:
    """RAG应用封装"""

    def __init__(self, persist_dir: str = CHROMA_PATH):
        self.persist_dir = persist_dir
        self.vectorstore = None
        self.qa_chain = None

    def index_documents(self, source: str):
        """索引文档（文件或目录）"""
        print(f"正在索引: {source}")

        if os.path.isfile(source):
            if source.endswith('.pdf'):
                documents = load_pdf_file(source)
            else:
                documents = load_text_file(source)
        elif os.path.isdir(source):
            documents = load_directory(source)
        else:
            raise FileNotFoundError(f"路径不存在: {source}")

        if not documents:
            raise ValueError("未加载到任何文档")

        print(f"加载了 {len(documents)} 个文档")
        self.vectorstore = create_vectorstore(documents, self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("索引完成!")

    def index_texts(self, texts: list, metadatas: list = None):
        """直接索引文本列表"""
        documents = []
        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {"source": f"text_{i}"}
            documents.append(Document(page_content=text, metadata=metadata))

        self.vectorstore = create_vectorstore(documents, self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("文本索引完成!")

    def load(self):
        """加载已有索引"""
        self.vectorstore = load_vectorstore(self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("已加载现有索引")

    def query(self, question: str) -> dict:
        """查询"""
        if not self.qa_chain:
            raise ValueError("请先索引文档或加载索引")

        result = self.qa_chain.invoke({"query": question})

        return {
            "answer": result["result"],
            "sources": [
                {
                    "content": doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in result["source_documents"]
            ]
        }

    def add_documents(self, source: str):
        """追加文档"""
        if not self.vectorstore:
            self.load()

        if os.path.isfile(source):
            if source.endswith('.pdf'):
                documents = load_pdf_file(source)
            else:
                documents = load_text_file(source)
        else:
            documents = load_directory(source)

        chunks = split_documents(documents)
        self.vectorstore.add_documents(chunks)
        print(f"已追加 {len(chunks)} 个文档片段")

    def search(self, query: str, k: int = 5) -> list:
        """相似度搜索（仅检索，不生成回答）"""
        if not self.vectorstore:
            raise ValueError("请先索引文档或加载索引")

        results = self.vectorstore.similarity_search(query, k=k)
        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in results
        ]


# ========== 6. 示例数据 ==========

SAMPLE_DOCUMENTS = [
    {
        "content": """公司员工手册 - 第一章：考勤制度

1. 工作时间
   - 标准工作时间：周一至周五，上午9:00-12:00，下午13:00-18:00
   - 午休时间：12:00-13:00
   - 每周工作时间不超过40小时

2. 打卡规定
   - 所有员工需通过公司APP或打卡机进行上下班打卡
   - 迟到定义：超过9:15到达视为迟到
   - 早退定义：未经批准在17:30前离开视为早退
   - 每月迟到/早退超过3次将影响绩效考核

3. 请假流程
   - 提前一天在OA系统提交申请
   - 由直属上级审批
   - 紧急情况可先电话请假，事后补交申请
   - 病假需提供医院证明

4. 年假规定
   - 入职满一年后享有5天年假
   - 每增加一年工龄增加1天，最多15天
   - 年假需提前3天申请
   - 当年未休完的年假可顺延至次年第一季度

5. 加班规定
   - 加班需提前在系统中申请
   - 工作日加班按1.5倍计算
   - 周末加班按2倍计算
   - 法定节假日加班按3倍计算
   - 可选择调休或加班费""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "考勤制度"}
    },
    {
        "content": """公司员工手册 - 第二章：报销制度

1. 报销原则
   - 费用必须与工作相关
   - 需提供正规发票或收据
   - 报销需在费用发生后30天内提交

2. 差旅报销
   - 需在出差结束后5个工作日内提交
   - 需附出差申请单、行程单、发票等

3. 交通费标准
   - 市内交通每日上限100元
   - 出租车需在公司APP叫车或保留发票
   - 长途交通：火车二等座、飞机经济舱

4. 住宿费标准
   - 一线城市（北上广深）：每晚上限500元
   - 二线城市：每晚上限400元
   - 其他城市：每晚上限300元
   - 需通过公司合作平台预订

5. 餐饮费标准
   - 出差期间每日餐饮上限150元
   - 商务宴请需提前申请，标准另行规定

6. 报销流程
   - 第一步：填写报销单，附上所有票据
   - 第二步：部门经理审批
   - 第三步：财务部审核
   - 第四步：审核通过后5个工作日内打款到工资账户""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "报销制度"}
    },
    {
        "content": """公司员工手册 - 第三章：福利制度

1. 社会保险
   - 公司按国家规定缴纳五险一金
   - 包括：养老保险、医疗保险、失业保险、工伤保险、生育保险、住房公积金
   - 公积金缴纳比例：公司12%，个人12%

2. 补充保险
   - 公司为正式员工购买补充医疗保险
   - 补充医疗保险可报销社保外的医疗费用，年度上限5万元
   - 为管理层购买商业意外险

3. 节日福利
   - 春节：发放礼品或购物卡（价值500元）
   - 中秋节：发放月饼礼盒
   - 端午节：发放粽子礼盒
   - 妇女节：女员工半天假+礼品

4. 生日福利
   - 生日当月发放200元生日礼金
   - 部门组织生日会

5. 健康福利
   - 每年一次免费体检
   - 健身房补贴：每月200元
   - 心理咨询服务：每年6次免费咨询

6. 团建活动
   - 每季度组织一次团队活动
   - 年度旅游：根据公司业绩安排

7. 培训机会
   - 每年可申请外部培训
   - 公司承担费用上限5000元
   - 需与工作相关并签订服务协议

8. 其他福利
   - 结婚礼金：1000元
   - 生育礼金：2000元
   - 丧葬慰问金：2000元
   - 住院慰问：500元""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "福利制度"}
    },
    {
        "content": """公司员工手册 - 第四章：绩效考核

1. 考核周期
   - 季度考核：每季度末进行
   - 年度考核：每年12月进行

2. 考核维度
   - 工作业绩（50%）：KPI完成情况
   - 工作能力（30%）：专业技能、学习能力、创新能力
   - 工作态度（20%）：责任心、团队协作、主动性

3. 考核等级
   - A级（优秀）：10%名额，绩效系数1.5
   - B级（良好）：30%名额，绩效系数1.2
   - C级（合格）：50%名额，绩效系数1.0
   - D级（待改进）：10%名额，绩效系数0.8

4. 考核结果应用
   - 与年终奖挂钩
   - 作为晋升参考
   - 连续两次D级将进行绩效改进计划

5. 申诉机制
   - 员工对考核结果有异议可在5个工作日内申诉
   - 由HR部门组织复核""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "绩效考核"}
    }
]


# ========== 7. 交互模式 ==========

def interactive_mode(rag: RAGApplication):
    """交互式问答"""
    print("\n" + "="*60)
    print("  RAG 问答系统 - 交互模式")
    print("  基于公司员工手册的智能问答")
    print("  - 输入问题进行查询")
    print("  - 输入 'search:关键词' 进行相似度搜索")
    print("  - 输入 'quit' 或 'exit' 退出")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("\n问题: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("再见!")
                break

            if user_input.startswith('search:'):
                # 相似度搜索模式
                query = user_input[7:].strip()
                results = rag.search(query, k=3)
                print("\n" + "-"*40)
                print("搜索结果:")
                for i, r in enumerate(results, 1):
                    print(f"\n[{i}] {r['metadata']}")
                    print(f"    {r['content'][:150]}...")
            else:
                # 问答模式
                result = rag.query(user_input)
                print("\n" + "-"*40)
                print(f"回答: {result['answer']}")
                print("\n参考来源:")
                for i, source in enumerate(result['sources'], 1):
                    chapter = source['metadata'].get('chapter', 'N/A')
                    print(f"  [{i}] {chapter}: {source['content'][:80]}...")

        except KeyboardInterrupt:
            print("\n\n已中断")
            break
        except Exception as e:
            print(f"\n错误: {e}")


def run_demo(rag: RAGApplication):
    """运行演示"""
    questions = [
        "公司的工作时间是什么？",
        "年假有多少天？怎么计算的？",
        "出差住宿费的标准是多少？",
        "公司有哪些福利？",
        "绩效考核是怎么评定的？",
        "加班费怎么计算？"
    ]

    print("\n" + "="*60)
    print("  RAG 示例演示")
    print("="*60)

    for q in questions:
        print(f"\n{'='*50}")
        print(f"问题: {q}")
        print('='*50)

        result = rag.query(q)
        print(f"\n回答: {result['answer']}")
        print("\n参考来源:")
        for i, source in enumerate(result['sources'], 1):
            chapter = source['metadata'].get('chapter', 'N/A')
            print(f"  [{i}] {chapter}")


# ========== 主程序 ==========

if __name__ == "__main__":
    import sys

    # 初始化RAG应用
    rag = RAGApplication()

    # 检查是否已有索引
    if os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH):
        print("检测到已有索引，正在加载...")
        rag.load()
    else:
        print("创建示例文档索引...")
        # 使用示例数据创建索引
        texts = [doc["content"] for doc in SAMPLE_DOCUMENTS]
        metadatas = [doc["metadata"] for doc in SAMPLE_DOCUMENTS]
        rag.index_texts(texts, metadatas)

    # 运行模式
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            run_demo(rag)
        elif sys.argv[1] == "--index" and len(sys.argv) > 2:
            # 索引指定文档
            rag.index_documents(sys.argv[2])
        elif sys.argv[1] == "--add" and len(sys.argv) > 2:
            # 追加文档
            rag.add_documents(sys.argv[2])
        else:
            print("用法:")
            print("  python rag_example.py          # 交互模式")
            print("  python rag_example.py --demo   # 运行演示")
            print("  python rag_example.py --index <path>  # 索引文档")
            print("  python rag_example.py --add <path>    # 追加文档")
    else:
        interactive_mode(rag)
