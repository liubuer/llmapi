"""
LangChain Agentサンプル

機能：
- 複数のツール定義（計算機、時刻照会、ファイル読み取りなど）
- Agentがユーザーの質問に応じて適切なツールを自動選択
- マルチターン対話とツールチェーン呼び出しに対応

依存関係のインストール：
    pip install langchain langchain-openai langchainhub

実行前にAPIサービスが起動していることを確認：
    start.bat api
"""
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool
from langchain import hub
from datetime import datetime


# ========== 1. LLMの作成 ==========
llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="gpt-5",
    temperature=0
)


# ========== 2. ツールの定義 ==========

@tool
def calculator(expression: str) -> str:
    """数学式を計算します。入力は '2 + 2' や '100 * 0.15' などの有効な数学式である必要があります"""
    try:
        # 安全な数学計算（数字と基本演算子のみ許可）
        allowed_chars = set('0123456789+-*/.() ')
        if not all(c in allowed_chars for c in expression):
            return "エラー：式に不正な文字が含まれています"
        result = eval(expression)
        return f"計算結果: {expression} = {result}"
    except Exception as e:
        return f"計算エラー: {e}"


@tool
def get_current_time() -> str:
    """現在時刻を取得します。ユーザーが現在の時刻を尋ねた時に使用します。"""
    now = datetime.now()
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    return f"現在時刻: {now.strftime('%Y年%m月%d日 %H:%M:%S')} ({weekdays[now.weekday()]}曜日)"


@tool
def search_info(query: str) -> str:
    """情報を検索します。知識、ニュース、天気などの情報を調べる必要がある時に使用します。"""
    # 検索結果のモック（実際のアプリケーションでは検索APIに接続可能）
    mock_results = {
        "天気": "本日は晴れ、気温15-22度、外出に適しています。空気質は良好です。",
        "ニュース": "本日のホットニュース：1. テック企業が新製品を発表 2. 株式市場は安定推移 3. 国際会議が開催",
        "為替": "本日の為替レート：1ドル = 150円、1ユーロ = 163円、1人民元 = 21円",
        "python": "Pythonは高水準プログラミング言語で、簡潔で読みやすいことで知られ、Web開発、データサイエンス、AI等の分野で広く使用されています。",
    }

    query_lower = query.lower()
    for key, value in mock_results.items():
        if key in query_lower:
            return value
    return f"'{query}' の検索結果：一般的なクエリです。公式ドキュメントや専門資料を参照してください。"


@tool
def file_reader(filepath: str) -> str:
    """ローカルファイルの内容を読み取ります。ファイルの完全パスを入力すると、ファイル内容を返します。テキストファイルや設定ファイルの読み取りに使用します。"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if len(content) > 2000:
                content = content[:2000] + "\n...(内容が長すぎるため、切り詰められました)"
            return f"ファイル内容:\n{content}"
    except FileNotFoundError:
        return f"エラー：ファイルが存在しません - {filepath}"
    except PermissionError:
        return f"エラー：ファイルの読み取り権限がありません - {filepath}"
    except Exception as e:
        return f"ファイル読み取りエラー: {e}"


@tool
def unit_converter(query: str) -> str:
    """単位変換ツール。長さ、重さ、温度などの単位変換に対応。
    入力形式例：'100 cm to m', '5 kg to g', '25 celsius to fahrenheit'"""
    try:
        parts = query.lower().replace('to', ' ').split()
        if len(parts) < 3:
            return "入力形式エラー。'数値 元単位 to 変換先単位' の形式で入力してください（例：'100 cm to m'）"

        value = float(parts[0])
        from_unit = parts[1]
        to_unit = parts[-1]

        # 長さ変換
        length_units = {
            'mm': 0.001, 'cm': 0.01, 'm': 1, 'km': 1000,
            'inch': 0.0254, 'ft': 0.3048, 'mile': 1609.34
        }

        # 重さ変換
        weight_units = {
            'mg': 0.001, 'g': 1, 'kg': 1000,
            'oz': 28.3495, 'lb': 453.592
        }

        # 温度変換
        if from_unit in ['celsius', 'c'] and to_unit in ['fahrenheit', 'f']:
            result = value * 9/5 + 32
            return f"{value}°C = {result:.2f}°F"
        elif from_unit in ['fahrenheit', 'f'] and to_unit in ['celsius', 'c']:
            result = (value - 32) * 5/9
            return f"{value}°F = {result:.2f}°C"

        # 長さ変換
        if from_unit in length_units and to_unit in length_units:
            meters = value * length_units[from_unit]
            result = meters / length_units[to_unit]
            return f"{value} {from_unit} = {result:.4f} {to_unit}"

        # 重さ変換
        if from_unit in weight_units and to_unit in weight_units:
            grams = value * weight_units[from_unit]
            result = grams / weight_units[to_unit]
            return f"{value} {from_unit} = {result:.4f} {to_unit}"

        return f"対応していない単位変換: {from_unit} -> {to_unit}"

    except ValueError:
        return "数値形式エラー。有効な数値を入力してください"
    except Exception as e:
        return f"変換エラー: {e}"


# ツールリスト
tools = [calculator, get_current_time, search_info, file_reader, unit_converter]


# ========== 3. Agentの作成 ==========

def create_agent():
    """Agentエグゼキューターを作成"""
    # ReActプロンプトテンプレートを使用（推論+行動）
    # このテンプレートはLLMに思考、ツール選択、実行、結果観察のサイクルを導きます
    prompt = hub.pull("hwchase17/react")

    # Agentを作成
    agent = create_react_agent(llm, tools, prompt)

    # エグゼキューターを作成
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,           # 詳細な思考プロセスを表示
        max_iterations=5,       # 最大イテレーション回数、無限ループを防止
        handle_parsing_errors=True,  # パースエラーを自動処理
        return_intermediate_steps=True  # 中間ステップを返却
    )

    return agent_executor


# ========== 4. インタラクティブ対話 ==========

def interactive_chat(agent_executor):
    """インタラクティブ対話"""
    print("\n" + "="*60)
    print("  LangChain Agent インタラクティブモード")
    print("  - 時刻の確認、計算、情報検索、ファイル読み取りなどが可能")
    print("  - 'quit' または 'exit' で終了")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("\nあなた: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("さようなら!")
                break

            print("\n" + "-"*40)
            result = agent_executor.invoke({"input": user_input})
            print("-"*40)
            print(f"\nAgent: {result['output']}")

        except KeyboardInterrupt:
            print("\n\n中断されました")
            break
        except Exception as e:
            print(f"\nエラー: {e}")


# ========== 5. サンプル実行 ==========

def run_examples(agent_executor):
    """サンプル質問を実行"""
    examples = [
        "今何時ですか？",
        "(125 * 0.8 + 50) / 2 を計算してください",
        "100摂氏度を華氏に変換してください",
        "今日の天気を検索してください",
        "5キロメートルは何マイルですか？",
    ]

    print("\n" + "="*60)
    print("  Agent サンプルデモ")
    print("="*60)

    for question in examples:
        print(f"\n{'='*50}")
        print(f"質問: {question}")
        print('='*50)

        try:
            result = agent_executor.invoke({"input": question})
            print(f"\n回答: {result['output']}")
        except Exception as e:
            print(f"\nエラー: {e}")

        print()


# ========== メインプログラム ==========

if __name__ == "__main__":
    import sys

    print("Agentを初期化中...")
    agent_executor = create_agent()
    print("Agent初期化完了!")

    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # サンプル実行
        run_examples(agent_executor)
    else:
        # インタラクティブモード
        interactive_chat(agent_executor)
