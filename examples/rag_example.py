"""
LangChain RAG（検索拡張生成）サンプル

機能：
- Chromaベクトルデータベースにドキュメントを保存
- 複数のドキュメント形式に対応（TXT、PDF）
- ドキュメントの分割とベクトル化
- 検索に基づく質疑応答

依存関係のインストール：
    pip install langchain langchain-openai langchain-community
    pip install chromadb sentence-transformers
    pip install pypdf  # PDFサポート

実行前にAPIサービスが起動していることを確認：
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


# ========== 1. 設定 ==========

# LLM設定 - ローカルAPIに接続
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5",
    temperature=0
)

# Embeddingモデル - HuggingFaceローカルモデルを使用（外部API不要）
# 初回実行時にモデルを自動ダウンロード（約500MB）
print("Embeddingモデルを読み込み中...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
print("Embeddingモデルの読み込み完了!")

# ベクトルデータベースの保存パス
CHROMA_PATH = "./chroma_db"


# ========== 2. ドキュメント処理 ==========

def load_text_file(filepath: str) -> list:
    """テキストファイルを読み込み"""
    from langchain_community.document_loaders import TextLoader
    loader = TextLoader(filepath, encoding='utf-8')
    return loader.load()


def load_pdf_file(filepath: str) -> list:
    """PDFファイルを読み込み"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(filepath)
        return loader.load()
    except ImportError:
        print("pypdfをインストールしてください: pip install pypdf")
        return []


def load_directory(dir_path: str) -> list:
    """ディレクトリ内の全ドキュメントを読み込み"""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader

    documents = []

    # txtファイルを読み込み
    txt_loader = DirectoryLoader(
        dir_path,
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={'encoding': 'utf-8'}
    )
    documents.extend(txt_loader.load())

    # pdfファイルを読み込み
    try:
        from langchain_community.document_loaders import PyPDFLoader
        pdf_loader = DirectoryLoader(
            dir_path,
            glob="**/*.pdf",
            loader_cls=PyPDFLoader
        )
        documents.extend(pdf_loader.load())
    except ImportError:
        print("ヒント：pypdfをインストールするとPDFファイルに対応できます")

    return documents


def split_documents(documents: list, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """ドキュメントを分割"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
    )
    return text_splitter.split_documents(documents)


# ========== 3. ベクトルデータベース ==========

def create_vectorstore(documents: list, persist_dir: str = CHROMA_PATH):
    """ベクトルデータベースを作成"""
    # ドキュメントを分割
    chunks = split_documents(documents)
    print(f"ドキュメント分割完了、合計 {len(chunks)} 個のフラグメント")

    # ベクトルデータベースを作成
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir
    )
    print(f"ベクトルデータベースを作成しました: {persist_dir}")
    return vectorstore


def load_vectorstore(persist_dir: str = CHROMA_PATH):
    """既存のベクトルデータベースを読み込み"""
    if not os.path.exists(persist_dir):
        raise FileNotFoundError(f"ベクトルデータベースが存在しません: {persist_dir}")

    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings
    )


# ========== 4. RAGチェーン ==========

def create_qa_chain(vectorstore, k: int = 3):
    """質疑応答チェーンを作成"""

    # リトリーバー
    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )

    # カスタムプロンプトテンプレート
    prompt_template = """あなたはプロフェッショナルな質疑応答アシスタントです。以下の参考情報に基づいて質問に回答してください。

要件：
1. 提供された参考情報のみに基づいて回答し、作り話をしないでください
2. 参考情報に関連する内容がない場合は、「既知の情報では回答できません」と明確に述べてください
3. 回答は正確、簡潔、専門的であること

参考情報：
{context}

質問：{question}

回答："""

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    # 質疑応答チェーンを作成
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt}
    )

    return qa_chain


# ========== 5. RAGアプリケーションクラス ==========

class RAGApplication:
    """RAGアプリケーションのラッパー"""

    def __init__(self, persist_dir: str = CHROMA_PATH):
        self.persist_dir = persist_dir
        self.vectorstore = None
        self.qa_chain = None

    def index_documents(self, source: str):
        """ドキュメントをインデックス化（ファイルまたはディレクトリ）"""
        print(f"インデックス作成中: {source}")

        if os.path.isfile(source):
            if source.endswith('.pdf'):
                documents = load_pdf_file(source)
            else:
                documents = load_text_file(source)
        elif os.path.isdir(source):
            documents = load_directory(source)
        else:
            raise FileNotFoundError(f"パスが存在しません: {source}")

        if not documents:
            raise ValueError("ドキュメントが読み込めませんでした")

        print(f"{len(documents)} 個のドキュメントを読み込みました")
        self.vectorstore = create_vectorstore(documents, self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("インデックス作成完了!")

    def index_texts(self, texts: list, metadatas: list = None):
        """テキストリストを直接インデックス化"""
        documents = []
        for i, text in enumerate(texts):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {"source": f"text_{i}"}
            documents.append(Document(page_content=text, metadata=metadata))

        self.vectorstore = create_vectorstore(documents, self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("テキストのインデックス作成完了!")

    def load(self):
        """既存のインデックスを読み込み"""
        self.vectorstore = load_vectorstore(self.persist_dir)
        self.qa_chain = create_qa_chain(self.vectorstore)
        print("既存のインデックスを読み込みました")

    def query(self, question: str) -> dict:
        """クエリ"""
        if not self.qa_chain:
            raise ValueError("先にドキュメントをインデックス化するか、インデックスを読み込んでください")

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
        """ドキュメントを追加"""
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
        print(f"{len(chunks)} 個のドキュメントフラグメントを追加しました")

    def search(self, query: str, k: int = 5) -> list:
        """類似度検索（検索のみ、回答生成なし）"""
        if not self.vectorstore:
            raise ValueError("先にドキュメントをインデックス化するか、インデックスを読み込んでください")

        results = self.vectorstore.similarity_search(query, k=k)
        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in results
        ]


# ========== 6. サンプルデータ ==========

SAMPLE_DOCUMENTS = [
    {
        "content": """社員ハンドブック - 第一章：勤怠制度

1. 勤務時間
   - 標準勤務時間：月曜日から金曜日、午前9:00-12:00、午後13:00-18:00
   - 昼休み：12:00-13:00
   - 週間勤務時間は40時間を超えないこと

2. 打刻規定
   - 全社員は会社のアプリまたは打刻機で出退勤の打刻を行うこと
   - 遅刻の定義：9:15を超えて到着した場合は遅刻とみなす
   - 早退の定義：承認なく17:30前に退社した場合は早退とみなす
   - 月間の遅刻/早退が3回を超えると人事評価に影響

3. 休暇申請手順
   - 1日前にOAシステムで申請を提出
   - 直属上司が承認
   - 緊急の場合は電話で事前連絡し、事後申請を提出
   - 病気休暇は病院の証明書が必要

4. 年次有給休暇規定
   - 入社1年後に5日の年次有給休暇を付与
   - 勤続年数1年増加ごとに1日追加、最大15日
   - 年次有給休暇は3日前に申請が必要
   - 当年度未消化の年次有給休暇は翌年度第1四半期まで繰り越し可能

5. 残業規定
   - 残業は事前にシステムで申請が必要
   - 平日の残業は1.5倍で計算
   - 週末の残業は2倍で計算
   - 法定祝日の残業は3倍で計算
   - 振替休日または残業手当を選択可能""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "勤怠制度"}
    },
    {
        "content": """社員ハンドブック - 第二章：経費精算制度

1. 精算原則
   - 費用は業務に関連するものであること
   - 正規の領収書またはレシートの提出が必要
   - 精算は費用発生後30日以内に提出すること

2. 出張経費精算
   - 出張終了後5営業日以内に提出すること
   - 出張申請書、行程表、領収書等を添付すること

3. 交通費基準
   - 市内交通は1日あたり上限10,000円
   - タクシーは会社のアプリで手配するか、領収書を保管すること
   - 長距離交通：新幹線普通車、飛行機エコノミークラス

4. 宿泊費基準
   - 東京・大阪等の大都市：1泊あたり上限15,000円
   - その他の都市：1泊あたり上限10,000円
   - 会社提携プラットフォームでの予約が必要

5. 食事代基準
   - 出張期間中の食事代は1日あたり上限3,000円
   - 接待は事前申請が必要、基準は別途規定

6. 精算手順
   - 第一ステップ：精算書に記入し、全ての証票を添付
   - 第二ステップ：部門マネージャーの承認
   - 第三ステップ：経理部の審査
   - 第四ステップ：審査通過後5営業日以内に給与口座に振込""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "経費精算制度"}
    },
    {
        "content": """社員ハンドブック - 第三章：福利厚生制度

1. 社会保険
   - 会社は法律に基づき社会保険と厚生年金に加入
   - 健康保険、厚生年金保険、雇用保険、労災保険を含む

2. 補充保険
   - 会社は正社員に団体医療保険を提供
   - 団体医療保険は社会保険適用外の医療費をカバー、年間上限50万円
   - 管理職には商業傷害保険を提供

3. 祝日福利
   - 年末年始：ギフトまたは商品券を支給（5,000円相当）
   - お盆：ギフトセットを支給
   - ゴールデンウィーク：特別休暇

4. 誕生日福利
   - 誕生月に20,000円の誕生日祝い金を支給
   - 部門で誕生日会を開催

5. 健康福利
   - 年1回の無料健康診断
   - フィットネスジム補助：月額5,000円
   - メンタルヘルス相談サービス：年6回無料相談

6. チームビルディング活動
   - 四半期ごとにチーム活動を1回開催
   - 年間旅行：会社の業績に応じて実施

7. 研修機会
   - 毎年外部研修を申請可能
   - 会社負担の上限は50万円
   - 業務関連であり、サービス契約の締結が必要

8. その他の福利
   - 結婚祝い金：50,000円
   - 出産祝い金：100,000円
   - 弔慰金：100,000円
   - 入院見舞金：30,000円""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "福利厚生制度"}
    },
    {
        "content": """社員ハンドブック - 第四章：人事評価

1. 評価サイクル
   - 四半期評価：各四半期末に実施
   - 年度評価：毎年12月に実施

2. 評価項目
   - 業務実績（50%）：KPI達成状況
   - 業務能力（30%）：専門スキル、学習能力、イノベーション能力
   - 業務態度（20%）：責任感、チームワーク、主体性

3. 評価ランク
   - Aランク（優秀）：10%の枠、評価係数1.5
   - Bランク（良好）：30%の枠、評価係数1.2
   - Cランク（合格）：50%の枠、評価係数1.0
   - Dランク（改善必要）：10%の枠、評価係数0.8

4. 評価結果の活用
   - 年末賞与と連動
   - 昇進の参考資料
   - 連続2回Dランクの場合は業績改善計画を実施

5. 異議申し立て制度
   - 社員は評価結果に対して5営業日以内に異議申し立て可能
   - 人事部が再審査を実施""",
        "metadata": {"source": "employee_handbook.txt", "chapter": "人事評価"}
    }
]


# ========== 7. インタラクティブモード ==========

def interactive_mode(rag: RAGApplication):
    """インタラクティブ質疑応答"""
    print("\n" + "="*60)
    print("  RAG 質疑応答システム - インタラクティブモード")
    print("  社員ハンドブックに基づくスマート質疑応答")
    print("  - 質問を入力してクエリ")
    print("  - 'search:キーワード' で類似度検索")
    print("  - 'quit' または 'exit' で終了")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("\n質問: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("さようなら!")
                break

            if user_input.startswith('search:'):
                # 類似度検索モード
                query = user_input[7:].strip()
                results = rag.search(query, k=3)
                print("\n" + "-"*40)
                print("検索結果:")
                for i, r in enumerate(results, 1):
                    print(f"\n[{i}] {r['metadata']}")
                    print(f"    {r['content'][:150]}...")
            else:
                # 質疑応答モード
                result = rag.query(user_input)
                print("\n" + "-"*40)
                print(f"回答: {result['answer']}")
                print("\n参考ソース:")
                for i, source in enumerate(result['sources'], 1):
                    chapter = source['metadata'].get('chapter', 'N/A')
                    print(f"  [{i}] {chapter}: {source['content'][:80]}...")

        except KeyboardInterrupt:
            print("\n\n中断されました")
            break
        except Exception as e:
            print(f"\nエラー: {e}")


def run_demo(rag: RAGApplication):
    """デモを実行"""
    questions = [
        "会社の勤務時間は何時から何時までですか？",
        "年次有給休暇は何日ありますか？どのように計算されますか？",
        "出張時の宿泊費の基準はいくらですか？",
        "会社にはどのような福利厚生がありますか？",
        "人事評価はどのように行われますか？",
        "残業手当はどのように計算されますか？"
    ]

    print("\n" + "="*60)
    print("  RAG サンプルデモ")
    print("="*60)

    for q in questions:
        print(f"\n{'='*50}")
        print(f"質問: {q}")
        print('='*50)

        result = rag.query(q)
        print(f"\n回答: {result['answer']}")
        print("\n参考ソース:")
        for i, source in enumerate(result['sources'], 1):
            chapter = source['metadata'].get('chapter', 'N/A')
            print(f"  [{i}] {chapter}")


# ========== メインプログラム ==========

if __name__ == "__main__":
    import sys

    # RAGアプリケーションを初期化
    rag = RAGApplication()

    # 既存のインデックスがあるか確認
    if os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH):
        print("既存のインデックスを検出、読み込み中...")
        rag.load()
    else:
        print("サンプルドキュメントのインデックスを作成中...")
        # サンプルデータでインデックスを作成
        texts = [doc["content"] for doc in SAMPLE_DOCUMENTS]
        metadatas = [doc["metadata"] for doc in SAMPLE_DOCUMENTS]
        rag.index_texts(texts, metadatas)

    # 実行モード
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            run_demo(rag)
        elif sys.argv[1] == "--index" and len(sys.argv) > 2:
            # 指定ドキュメントをインデックス化
            rag.index_documents(sys.argv[2])
        elif sys.argv[1] == "--add" and len(sys.argv) > 2:
            # ドキュメントを追加
            rag.add_documents(sys.argv[2])
        else:
            print("使用方法:")
            print("  python rag_example.py          # インタラクティブモード")
            print("  python rag_example.py --demo   # デモを実行")
            print("  python rag_example.py --index <path>  # ドキュメントをインデックス化")
            print("  python rag_example.py --add <path>    # ドキュメントを追加")
    else:
        interactive_mode(rag)
