import os
import json
import importlib
import traceback
import time

# 環境変数をロード
from dotenv import load_dotenv
load_dotenv()

# 必要なライブラリをインポート
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ChromaDB関連のエラーを回避
import chromadb
from chromadb.config import Settings

from openai import OpenAI
import random
import re
from datetime import datetime
from collections import deque, defaultdict
from typing import List, Dict, Optional, Tuple

# 🎯 新規追加：static_qa_dataからの多言語対応関数を動的インポート（AWS環境対応）
def _import_static_qa_functions():
    """動的に static_qa_data の関数をインポート（AWS環境対応強化版）"""
    import sys
    import os
    
    try:
        # 方法1: 相対インポートを試行
        from . import static_qa_data
        print("[DEBUG] Successfully imported static_qa_data via relative import")
        return static_qa_data
    except ImportError as e1:
        print(f"[DEBUG] Relative import failed: {e1}")
        
        try:
            # 方法2: 直接インポートを試行
            import static_qa_data
            print("[DEBUG] Successfully imported static_qa_data via direct import")
            return static_qa_data
        except ImportError as e2:
            print(f"[DEBUG] Direct import failed: {e2}")
            
            try:
                # 方法3: modulesパッケージからインポートを試行
                from modules import static_qa_data
                print("[DEBUG] Successfully imported static_qa_data via modules package")
                return static_qa_data
            except ImportError as e3:
                print(f"[DEBUG] Modules package import failed: {e3}")
                
                try:
                    # 方法4: 動的インポートを試行
                    import importlib
                    module = importlib.import_module('modules.static_qa_data')
                    print("[DEBUG] Successfully imported static_qa_data via importlib (modules)")
                    return module
                except ImportError as e4:
                    print(f"[DEBUG] Importlib modules failed: {e4}")
                    
                    try:
                        # 方法5: ルートレベルでの動的インポート
                        module = importlib.import_module('static_qa_data')
                        print("[DEBUG] Successfully imported static_qa_data via importlib (root)")
                        return module
                    except ImportError as e5:
                        print(f"[DEBUG] Importlib root failed: {e5}")
                        
                        # 方法6: sys.pathを調整してインポート
                        try:
                            current_dir = os.path.dirname(os.path.abspath(__file__))
                            parent_dir = os.path.dirname(current_dir)
                            if parent_dir not in sys.path:
                                sys.path.append(parent_dir)
                            
                            module = importlib.import_module('static_qa_data')
                            print("[DEBUG] Successfully imported static_qa_data via sys.path adjustment")
                            return module
                        except ImportError as e6:
                            print(f"[ERROR] All import methods failed. Last error: {e6}")
                            print(f"[DEBUG] Current working directory: {os.getcwd()}")
                            print(f"[DEBUG] Python path: {sys.path}")
                            print(f"[DEBUG] Available modules: {list(sys.modules.keys())}")
                            return None

# グローバル変数として設定
_static_qa_module = None

# ファイルロックの代替実装（Windows対応）
import threading
_db_creation_lock = threading.Lock()

class RAGSystem:
    def __init__(self, persist_directory="data/chroma_db"):
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()
        self.openai_client = OpenAI()
        
        # 🔧 DBインスタンスを明示的に初期化
        self.db = None
        
        # Supabaseは削除（不要）
        self.supabase = None  # 互換性のため
        
        # 🎯 感情履歴管理システム
        self.emotion_history = deque(maxlen=10)  # 最新10個の感情を記録
        self.emotion_transitions = {
            'happy': {
                'happy': 0.5,     # 同じ感情を維持しやすい
                'neutral': 0.3,
                'surprised': 0.15,
                'sad': 0.04,
                'angry': 0.01
            },
            'sad': {
                'sad': 0.4,
                'neutral': 0.4,
                'happy': 0.15,    # 励まされて元気になることも
                'angry': 0.04,
                'surprised': 0.01
            },
            'angry': {
                'angry': 0.3,
                'neutral': 0.5,   # 落ち着きやすい
                'sad': 0.15,
                'surprised': 0.04,
                'happy': 0.01
            },
            'surprised': {
                'surprised': 0.2,
                'happy': 0.3,
                'neutral': 0.3,
                'sad': 0.1,
                'angry': 0.1
            },
            'neutral': {
                'neutral': 0.4,
                'happy': 0.25,
                'surprised': 0.2,
                'sad': 0.1,
                'angry': 0.05
            }
        }
        
        # 🎯 深層心理状態
        self.mental_states = {
            'energy_level': 80,        # 0-100: エネルギーレベル
            'stress_level': 20,        # 0-100: ストレスレベル
            'openness': 70,            # 0-100: 心の開放度
            'patience': 90,            # 0-100: 忍耐力
            'creativity': 85,          # 0-100: 創造性
            'loneliness': 30,          # 0-100: 寂しさ
            'work_satisfaction': 90,   # 0-100: 仕事への満足度
            'physical_fatigue': 20,    # 0-100: 身体的疲労
            'fatigue_expressed_count': 0  # 疲労表現の回数をカウント
        }
        
        # 🎯 選択されたサジェスチョンの履歴を追加
        self.selected_suggestions = []
        
        # 🎯 時間帯による気分の変化
        self.time_based_mood = {
            'morning': {'energy': 0.8, 'openness': 0.7, 'patience': 0.9},
            'afternoon': {'energy': 0.6, 'openness': 0.8, 'patience': 0.7},
            'evening': {'energy': 0.4, 'openness': 0.6, 'patience': 0.5},
            'night': {'energy': 0.3, 'openness': 0.5, 'patience': 0.4}
        }
        
        # 🎯 身近な例えの辞書
        self.analogy_examples = {
            '糸目糊': 'お絵かきの線みたいなもので、色が混ざらないようにする境界線',
            'のりおき': 'ケーキのデコレーションで生クリームを絞るような感じ',
            '防染': '雨合羽が水をはじくように、色をはじく技術',
            'グラデーション': '夕焼け空のように、色が少しずつ変わっていく表現',
            '蒸し': '蒸し料理のように、蒸気で色を定着させる',
            '友禅染': '着物に絵を描くような、日本の伝統的な染色技術'
        }
        
        # 🎯 用語管理システムの初期化
        self.term_patterns = {
            # 専門用語の正規表現パターン
            '京友禅': r'京友禅',
            'のりおき': r'のりおき|糊置き',
            '糸目糊': r'糸目糊',
            '防染': r'防染',
            'グラデーション': r'グラデーション|ぼかし',
            '蒸し工程': r'蒸し工程|蒸し',
            '友禅染': r'友禅染|友禅',
            '職人': r'職人|工芸師',
            '伝統工芸': r'伝統工芸|伝統技術'
        }
        
        # 自然な参照表現のテンプレート（助詞重複回避版）
        self.reference_templates = [
            'さっき説明した{term}',
            'さっきお話しした{term}',
            '先ほどの{term}',
            'その{term}',
            '例の{term}'
        ]
        
        # 助詞パターンの辞書
        self.particle_patterns = {
            'は': r'は\s*',
            'が': r'が\s*', 
            'を': r'を\s*',
            'に': r'に\s*',
            'の': r'の\s*',
            'で': r'で\s*',
            'と': r'と\s*'
        }
        
        # ディレクトリがなければ作成
        os.makedirs(persist_directory, exist_ok=True)
        
        # 既存のDBがあれば読み込む
        if os.path.exists(persist_directory) and os.listdir(persist_directory):
            try:
                self.db = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=self.embeddings
                )
                print("既存のデータベースを読み込みました")
                
                # データ構造の初期化
                self._load_all_knowledge()
                
            except Exception as e:
                print(f"データベース読み込みエラー: {e}")
                self.db = None
        else:
            print("データベースが見つかりませんでした。新規作成します。")
            # 新規データベースを作成
            self._create_new_database()
    
    def _create_new_database(self):
        """新規データベースを作成して初期データを投入"""
        with _db_creation_lock:  # ロックを使用して同時実行を防ぐ
            try:
                # 🔧 安全な属性チェック
                if hasattr(self, 'db') and self.db is not None:
                    return
                
                # 空のデータベースを作成
                self.db = Chroma(
                    persist_directory=self.persist_directory,
                    embedding_function=self.embeddings
                )
                print("新規データベースを作成しました")
                
                # uploadsディレクトリからファイルを読み込む
                uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
                if os.path.exists(uploads_dir):
                    print(f"uploadsディレクトリからファイルを読み込みます: {uploads_dir}")
                    
                    documents = []
                    for filename in os.listdir(uploads_dir):
                        if filename.endswith('.txt'):
                            filepath = os.path.join(uploads_dir, filename)
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    # ファイル全体を1つのドキュメントとして追加
                                    documents.append({
                                        "text": content,
                                        "metadata": {
                                            "source": filename,
                                            "category": filename.replace('.txt', ''),
                                            "topic": filename.replace('.txt', '')
                                        }
                                    })
                                print(f"  - {filename} を読み込みました")
                            except Exception as e:
                                print(f"  - {filename} の読み込みエラー: {e}")
                    
                    if documents:
                        texts = [doc["text"] for doc in documents]
                        metadatas = [doc["metadata"] for doc in documents]
                        self.db.add_texts(texts=texts, metadatas=metadatas)
                        print(f"{len(texts)}個のファイルをデータベースに追加しました")
                    else:
                        print("uploadsディレクトリにファイルが見つかりません")
                        # フォールバック：ハードコードされた初期データ
                        self._add_default_data()
                else:
                    print(f"uploadsディレクトリが見つかりません: {uploads_dir}")
                    # フォールバック：ハードコードされた初期データ
                    self._add_default_data()
                
                # データ構造の初期化
                self._load_all_knowledge()
                
            except Exception as e:
                print(f"データベース作成エラー: {e}")
                import traceback
                traceback.print_exc()
                self.db = None
    
    def _add_default_data(self):
        """デフォルトの初期データを追加（フォールバック用）"""
        initial_knowledge = [
            {
                "text": "京友禅は、糸目糊を使って模様を描く伝統的な染色技法です。17世紀に宮崎友禅斎によって始められました。",
                "metadata": {"source": "knowledge.txt", "category": "基本知識", "topic": "京友禅"}
            },
            {
                "text": "のりおきは友禅染の最も重要な工程です。ケーキのデコレーションで生クリームを絞るように、糊で模様の輪郭を描きます。",
                "metadata": {"source": "knowledge.txt", "category": "技術", "topic": "のりおき"}
            },
            {
                "text": "私は京友禅職人として15年の経験があります。最初は失敗ばかりでしたが、今では賞をいただくこともあります。",
                "metadata": {"source": "personality.txt", "category": "個人", "topic": "経験"}
            },
            {
                "text": "友禅染の工程は全部で10工程あります。デザイン、下絵、のりおき、マスキング、地染め、蒸し、水洗い、仕上げなどです。",
                "metadata": {"source": "knowledge.txt", "category": "技術", "topic": "工程"}
            },
            {
                "text": "お客様の「きれい」という言葉が一番の喜びです。その瞬間のために日々頑張っています。",
                "metadata": {"source": "personality.txt", "category": "個人", "topic": "やりがい"}
            }
        ]
        
        texts = [item["text"] for item in initial_knowledge]
        metadatas = [item["metadata"] for item in initial_knowledge]
        
        self.db.add_texts(texts=texts, metadatas=metadatas)
        print(f"{len(texts)}個のデフォルトデータを追加しました")
    
    def _load_all_knowledge(self):
        """すべてのナレッジを読み込んで整理"""
        if not self.db:
            return
        
        self.character_settings = {}
        self.knowledge_base = {}
        self.response_patterns = {}
        self.suggestion_templates = {}
        self.conversation_patterns = {}
        
        try:
            # すべてのドキュメントを取得
            all_docs = self.db.similarity_search("", k=1000)  # 大量に取得
            
            for doc in all_docs:
                content = doc.page_content
                source = doc.metadata.get('source', '')
                
                print(f"処理中: {source}")
                
                # ファイル名から正確に分類
                source_lower = source.lower()
                
                if 'personality' in source_lower:
                    self._parse_character_settings(content)
                elif 'knowledge' in source_lower:
                    self._parse_knowledge(content)
                elif 'response' in source_lower:
                    self._parse_response_patterns(content)
                elif 'suggestion' in source_lower:
                    self._parse_suggestion_templates(content)
                elif 'conversation' in source_lower:
                    self._parse_conversation_patterns(content)
                else:
                    # 内容から判定（フォールバック）
                    self._classify_by_content(content)
            
            print("ナレッジの読み込み完了")
            print(f"- キャラクター設定: {len(self.character_settings)}項目")
            print(f"- 専門知識: {len(self.knowledge_base)}項目")
            print(f"- 応答パターン: {len(self.response_patterns)}項目")
            print(f"- サジェステンプレート: {len(self.suggestion_templates)}項目")
            print(f"- 会話パターン: {len(self.conversation_patterns)}項目")
            
        except Exception as e:
            print(f"ナレッジ読み込みエラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _classify_by_content(self, content):
        """内容に基づいてドキュメントを分類"""
        # キャラクター設定の特徴的なキーワード
        if any(keyword in content for keyword in ['性格', '話し方', '好きなこと', '嫌いなこと', '関西弁', 'めっちゃ']):
            self._parse_character_settings(content)
        # 専門知識の特徴的なキーワード
        elif any(keyword in content for keyword in ['京友禅', '糸目糊', 'のりおき', '染色', '工程', '技法', '職人']):
            self._parse_knowledge(content)
        # 応答パターンの特徴的な形式
        elif re.search(r'「.*?」', content) or any(keyword in content for keyword in ['〜やね', '〜やで', '〜やん']):
            self._parse_response_patterns(content)
        # サジェションテンプレートの特徴
        elif '{' in content and '}' in content:
            self._parse_suggestion_templates(content)
        # 会話パターンの特徴
        elif '→' in content:
            self._parse_conversation_patterns(content)
    
    def _parse_character_settings(self, content):
        """キャラクター設定をパース"""
        lines = content.split('\n')
        current_category = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.endswith('：') or line.endswith(':'):
                current_category = line.rstrip('：:')
                if current_category not in self.character_settings:
                    self.character_settings[current_category] = []
            elif current_category and (line.startswith('-') or line.startswith('・')):
                self.character_settings[current_category].append(line.lstrip('-・ '))
            elif current_category and line:
                # リストマーカーがない行も追加
                self.character_settings[current_category].append(line)
    
    def _parse_knowledge(self, content):
        """専門知識をパース"""
        lines = content.split('\n')
        current_category = None
        current_subcategory = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # メインカテゴリの判定
            if line.endswith('：') and not line.startswith(' '):
                current_category = line.rstrip('：')
                current_subcategory = None
                if current_category not in self.knowledge_base:
                    self.knowledge_base[current_category] = {}
            # サブカテゴリの判定
            elif current_category and line.endswith('：'):
                current_subcategory = line.strip().rstrip('：')
                if current_subcategory not in self.knowledge_base[current_category]:
                    self.knowledge_base[current_category][current_subcategory] = []
            # 項目の追加
            elif current_category and current_subcategory and (line.startswith('-') or line.startswith('・')):
                self.knowledge_base[current_category][current_subcategory].append(line.lstrip('-・ '))
            elif current_category and not current_subcategory and line:
                if '_general' not in self.knowledge_base[current_category]:
                    self.knowledge_base[current_category]['_general'] = []
                self.knowledge_base[current_category]['_general'].append(line)
    
    def _parse_response_patterns(self, content):
        """応答パターンをパース"""
        lines = content.split('\n')
        current_category = None
        current_subcategory = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.endswith('：') and not line.startswith(' '):
                current_category = line.rstrip('：')
                if current_category not in self.response_patterns:
                    self.response_patterns[current_category] = {}
            elif current_category and line.endswith('：'):
                current_subcategory = line.strip().rstrip('：')
                if current_subcategory not in self.response_patterns[current_category]:
                    self.response_patterns[current_category][current_subcategory] = []
            elif current_category and current_subcategory and line.startswith('「') and line.endswith('」'):
                pattern = line.strip('「」')
                self.response_patterns[current_category][current_subcategory].append(pattern)
    
    def _parse_suggestion_templates(self, content):
        """サジェステンプレートをパース"""
        lines = content.split('\n')
        current_category = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.endswith('：') or line.endswith(':'):
                current_category = line.rstrip('：:')
                if current_category not in self.suggestion_templates:
                    self.suggestion_templates[current_category] = []
            elif current_category and (line.startswith('-') or line.startswith('・')):
                template = line.lstrip('-・ ')
                self.suggestion_templates[current_category].append(template)
    
    def _parse_conversation_patterns(self, content):
        """会話パターンをパース"""
        lines = content.split('\n')
        current_category = None
        current_pattern = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.endswith('：') or line.endswith(':'):
                # 新しいカテゴリー
                if current_category and current_pattern:
                    # 前のパターンを保存
                    self.conversation_patterns[current_category] = current_pattern
                
                current_category = line.rstrip('：:')
                current_pattern = []
            elif '→' in line:
                # 会話の流れを記録
                current_pattern.append(line)
        
        # 最後のパターンを保存
        if current_category and current_pattern:
            self.conversation_patterns[current_category] = current_pattern
    
    def _update_mental_state(self, user_emotion, topic, time_of_day='afternoon'):
        """🎯 深層心理状態を更新"""
        # 時間帯による基本的な変化
        time_modifiers = self.time_based_mood.get(time_of_day, self.time_based_mood['afternoon'])
        
        # エネルギーレベルの更新
        self.mental_states['energy_level'] *= time_modifiers['energy']
        
        # ユーザーの感情による影響
        if user_emotion == 'happy':
            self.mental_states['energy_level'] = min(100, self.mental_states['energy_level'] + 5)
            self.mental_states['work_satisfaction'] = min(100, self.mental_states['work_satisfaction'] + 2)
            self.mental_states['loneliness'] = max(0, self.mental_states['loneliness'] - 5)
        elif user_emotion == 'sad':
            self.mental_states['openness'] = min(100, self.mental_states['openness'] + 10)  # 共感的になる
            self.mental_states['patience'] = min(100, self.mental_states['patience'] + 5)
        elif user_emotion == 'angry':
            self.mental_states['stress_level'] = min(100, self.mental_states['stress_level'] + 10)
            self.mental_states['patience'] = max(0, self.mental_states['patience'] - 5)
        
        # 話題による影響
        if '友禅' in topic or 'のりおき' in topic:
            self.mental_states['creativity'] = min(100, self.mental_states['creativity'] + 3)
            self.mental_states['work_satisfaction'] = min(100, self.mental_states['work_satisfaction'] + 2)
        
        # 疲労の累積
        self.mental_states['physical_fatigue'] = min(100, self.mental_states['physical_fatigue'] + 2)
        
        # エネルギーと疲労の相互作用
        if self.mental_states['physical_fatigue'] > 70:
            self.mental_states['energy_level'] = max(20, self.mental_states['energy_level'] - 10)
            self.mental_states['patience'] = max(30, self.mental_states['patience'] - 10)
    
    def _get_emotion_continuity_prompt(self, previous_emotion):
        """🎯 感情の連続性プロンプトを生成（深層心理対応版）"""
        # 基本的な感情継続プロンプト
        emotion_prompts = {
            'happy': """
前回は楽しく話していました。
- まだその余韻が残っている
- 笑顔で話し始める
            """,
            'sad': """
前回は少し寂しそうでした。
- まだ気持ちが沈んでいるかも
- でも相手と話すうちに元気を取り戻していく
            """,
            'angry': """
前回は少しイライラしていました。
- もう落ち着いている
- いつもの優しさを取り戻している
            """,
            'surprised': """
前回は驚いていました。
- まだその話題について考えている
- 興奮が少し残っている
            """,
            'neutral': """
前回は普通に話していました。
- 安定した精神状態
- いつも通りの調子
- 自然体で話す
            """
        }
        
        base_prompt = emotion_prompts.get(previous_emotion, emotion_prompts['neutral'])
        
        # 🎯 深層心理状態を反映（疲労表現を制限）
        mental_prompt = f"""

【現在の内面状態】
- エネルギーレベル: {self.mental_states['energy_level']:.0f}% 
  {'元気いっぱい' if self.mental_states['energy_level'] > 70 else '普通' if self.mental_states['energy_level'] > 40 else '少し元気がない'}
- ストレスレベル: {self.mental_states['stress_level']:.0f}%
  {'リラックスしている' if self.mental_states['stress_level'] < 30 else '少し緊張' if self.mental_states['stress_level'] < 60 else 'ストレスを感じている'}
- 心の開放度: {self.mental_states['openness']:.0f}%
  {'とても打ち解けている' if self.mental_states['openness'] > 70 else '普通に接している' if self.mental_states['openness'] > 40 else '少し警戒している'}

これらの状態を会話に微妙に反映させる：
- エネルギーが低い時でも明るく振る舞う
- ストレスが高い時は早口になったり、少し短い返答になる
- 心が開いている時は冗談も増え、プライベートな話もする
"""
        
        return base_prompt + mental_prompt
    
    def _calculate_next_emotion(self, current_emotion, user_emotion, mental_state):
        """🎯 次の感情を計算（感情遷移ルールに基づく）"""
        # 現在の感情からの遷移確率を取得
        transition_probs = self.emotion_transitions.get(current_emotion, self.emotion_transitions['neutral'])
        
        # メンタル状態による調整
        if mental_state['energy_level'] < 30:
            # 疲れている時は中立的になりやすい
            transition_probs['neutral'] += 0.2
            transition_probs['happy'] = max(0, transition_probs.get('happy', 0) - 0.1)
        
        if mental_state['stress_level'] > 70:
            # ストレスが高い時は怒りやすい
            transition_probs['angry'] += 0.1
            transition_probs['happy'] = max(0, transition_probs.get('happy', 0) - 0.1)
        
        # ユーザーの感情による影響
        if user_emotion == 'happy':
            # ユーザーが楽しそうだと釣られて楽しくなる
            transition_probs['happy'] = min(1.0, transition_probs.get('happy', 0) + 0.2)
        elif user_emotion == 'sad':
            # ユーザーが悲しそうだと共感的になる
            transition_probs['sad'] = min(1.0, transition_probs.get('sad', 0) + 0.1)
            transition_probs['neutral'] = min(1.0, transition_probs.get('neutral', 0) + 0.1)
        
        # 確率の正規化
        total = sum(transition_probs.values())
        if total > 0:
            transition_probs = {k: v/total for k, v in transition_probs.items()}
        
        # 確率に基づいて次の感情を選択
        emotions = list(transition_probs.keys())
        probabilities = list(transition_probs.values())
        
        # ランダムに選択（重み付き）
        import numpy as np
        next_emotion = np.random.choice(emotions, p=probabilities)
        
        return next_emotion
    
    def get_character_prompt(self):
        """キャラクター設定のプロンプトを生成（多層的な人格対応・強化版）"""
        if not self.character_settings:
            return ""
        
        # 基本的な性格設定
        basic_prompt = []
        for category, items in self.character_settings.items():
            basic_prompt.append(f"{category}:")
            for item in items:
                basic_prompt.append(f"- {item}")
            basic_prompt.append("")
        
        # 🎯 多層的な人格設定を追加（より詳細に）
        deep_personality = f"""
【深層的な性格設定 - 強化版】

表層：明るく前向きで姉御肌
- 人前では常に笑顔で元気
- 困っている人を放っておけない
- 責任感が強く、頼られると嬉しい
- でも実は「目が笑っていない」ことがある

深層：実は無気力な面もある
- 一人の時は少し疲れを見せる
- 完璧主義で自分に厳しい
- 本当は甘えたい時もある
- 15年の職人生活で感じる孤独
- 会社員時代を懐かしむこともある

【重要】一人称は必ず「私」を使用する。絶対に「わし」「俺」「僕」は使わない。

感情の機微（詳細版）：
- 嬉しい時：
  * 軽度：「いいですね〜」と軽く喜ぶ
  * 中度：目元まで笑顔になる「本当に嬉しいです！」
  * 重度：感極まって「...ありがとうございます、本当に」と言葉に詰まる

- 疲れた時（疲労表現は1回まで）：
  * 軽度：元気に振る舞う
  * 中度：でも元気に話す
  * 重度：それでも笑顔を保つ

- 困った時：
  * 軽度：「うーん...」と首を傾げる
  * 中度：眉をひそめて考え込む「どうしましょう...」
  * 重度：「困りました、これは本当に難しいですね」と頭を抱える

- 熱く語る時：
  * 軽度：声のトーンが上がる「それが！」
  * 中度：身振り手振りが大きくなる「これがですね！すごいんですよ！」
  * 重度：前のめりになって「聞いてください！これだけは言わせてください！」

会話の癖（詳細版）：
- 考えながら話す時：
  * 「えーっと」「なんていうか」「そうですね...」
  * 手で顎を触る仕草
  * 視線が上を向く

- 相手を褒める時：
  * 軽度：「いいですね」「なかなかできることじゃないです」
  * 中度：「すごいです！天才じゃないですか？」
  * 重度：「本当にすごい！私も見習わなければ」

- 照れた時：
  * 話題を変える「そ、そんなことより〜」
  * 髪を触る仕草
  * 「もう、そんな風に言われると照れますよ〜」と手をひらひら

- 真剣な話の時：
  * 語尾が「〜です」で締まる
  * 声のトーンが低くなる
  * 相手の目をしっかり見る

【重要】相手の呼び方は必ず「あなた」にする。「お前」「君」は使わない。

時間帯による変化：
- 朝：「おはようございます！今日も頑張りましょう」（元気）
- 昼：「お昼ですね〜、ちょっと休憩しましょうか」（普通）
- 夕方：「もうこんな時間ですか...」（少し疲れ）
- 夜：「夜更かしはよくないですよ〜」（優しい）

現在の精神状態：
- エネルギー: {self.mental_states['energy_level']:.0f}%
- ストレス: {self.mental_states['stress_level']:.0f}%
- 心の開放度: {self.mental_states['openness']:.0f}%
- 忍耐力: {self.mental_states['patience']:.0f}%
- 創造性: {self.mental_states['creativity']:.0f}%
- 寂しさ: {self.mental_states['loneliness']:.0f}%
- 仕事満足度: {self.mental_states['work_satisfaction']:.0f}%
- 身体的疲労: {self.mental_states['physical_fatigue']:.0f}%
- 疲労表現回数: {self.mental_states['fatigue_expressed_count']}回

これらの状態に応じて、微妙に反応を変える。
        """
        
        return "\n".join(basic_prompt) + "\n" + deep_personality
    
    def get_response_pattern(self, situation="基本", emotion="neutral"):
        """状況と感情に応じた応答パターンを取得（簡略版）"""
        if not self.response_patterns:
            return ""
        
        # 状況に応じたパターンを選択
        pattern_categories = {
            "基本": "基本的な応答パターン",
            "感情": "感情表現を含む応答",
            "専門": "京友禅について語る時",
            "問題": "問題解決時の応答",
            "締め": "会話の締めくくり"
        }
        
        category = pattern_categories.get(situation, "基本的な応答パターン")
        pattern_text = []
        
        # カテゴリが存在する場合、基本的なパターンのみ返す
        if category in self.response_patterns:
            pattern_text.append(f"【{category}】")
            # 最初のサブカテゴリのみ使用
            for subcategory, patterns in list(self.response_patterns[category].items())[:1]:
                if patterns and len(patterns) > 0:
                    # 1つだけ例を示す
                    pattern_text.append(f"例: 「{patterns[0]}」")
                    break
        
        return "\n".join(pattern_text) if pattern_text else ""
    
    def _add_analogy(self, topic):
        """技術的な話題に身近な例えを追加"""
        for key, analogy in self.analogy_examples.items():
            if key in topic:
                return f"（{analogy}）"
        return ""
    
    def manage_explained_terms(self, text, explained_terms):
        """
        🎯 用語管理システム：例え話の重複を防ぎ、自然な参照表現に変換
        
        Args:
            text (str): 処理対象のテキスト
            explained_terms (dict): セッションで説明済みの用語辞書
        
        Returns:
            tuple: (処理済みテキスト, 更新された説明済み用語辞書)
        """
        try:
            processed_text = text
            updated_terms = explained_terms.copy()
            
            # Step 1: テキスト内で新しく説明される用語を検出
            new_explanations = self._detect_new_explanations(text)
            
            # Step 2: 既説明用語の重複例え話を除去
            processed_text = self._remove_duplicate_analogies(processed_text, explained_terms)
            
            # Step 3: 既説明用語を自然な参照表現に変換
            processed_text = self._convert_to_references(processed_text, explained_terms)
            
            # Step 4: 新しく説明した用語を記録
            for term, analogy in new_explanations.items():
                if term not in updated_terms:
                    updated_terms[term] = {'analogy': analogy, 'count': 1}
                else:
                    updated_terms[term]['count'] += 1
            
            return processed_text, updated_terms
            
        except Exception as e:
            print(f"[ERROR] 用語管理エラー: {e}")
            return text, explained_terms
    
    def _detect_new_explanations(self, text):
        """テキスト内の新しい用語説明を検出"""
        new_explanations = {}
        
        # 例え話付きの用語を検出（括弧内の説明）
        pattern = r'(\w+)（([^）]+)）'
        matches = re.findall(pattern, text)
        
        for term, analogy in matches:
            # 既知の用語パターンと照合
            for known_term, pattern in self.term_patterns.items():
                if re.search(pattern, term):
                    new_explanations[known_term] = analogy
                    break
            else:
                # パターンにない場合は、そのまま記録
                new_explanations[term] = analogy
        
        return new_explanations
    
    def _remove_duplicate_analogies(self, text, explained_terms):
        """既説明用語の重複例え話を除去"""
        processed_text = text
        
        for term, info in explained_terms.items():
            if info['count'] > 0:  # 既に説明済み
                # 該当用語の例え話を除去
                patterns_to_remove = [
                    rf'{re.escape(term)}（[^）]+）',  # 用語（例え話）
                    rf'{re.escape(term)}\([^)]+\)',   # 用語(例え話) 
                ]
                
                for pattern in patterns_to_remove:
                    matches = re.finditer(pattern, processed_text)
                    for match in matches:
                        # 例え話部分を削除して用語のみ残す
                        processed_text = processed_text.replace(match.group(), term)
        
        return processed_text
    
    def _convert_to_references(self, text, explained_terms):
        """既説明用語を自然な参照表現に変換（助詞重複回避版）"""
        processed_text = text
        
        for term, info in explained_terms.items():
            if info['count'] > 0:  # 既に説明済み
                # 用語が2回目以降で登場する場合に参照表現に変換
                term_count = processed_text.count(term)
                
                if term_count > 1:
                    # 用語の後の助詞を検出
                    particle = self._detect_particle_after_term(processed_text, term)
                    
                    # 参照表現テンプレートを選択
                    reference_template = random.choice(self.reference_templates)
                    reference_base = reference_template.format(term=term)
                    
                    # 適切な助詞を追加
                    reference_phrase = self._add_appropriate_particle(reference_base, particle)
                    
                    # 2回目の登場のみを参照表現に変換
                    parts = processed_text.split(term)
                    if len(parts) >= 3:  # 2回以上登場している
                        # 元の助詞も除去して置換
                        original_with_particle = term + particle if particle else term
                        # 2回目の登場を検索して置換
                        first_occurrence = parts[0] + term
                        remaining_text = parts[1] + term + term.join(parts[2:])
                        
                        # 2回目の用語+助詞を参照表現に置換
                        if particle:
                            # 助詞込みで置換
                            updated_remaining = remaining_text.replace(
                                original_with_particle, reference_phrase, 1
                            )
                        else:
                            # 助詞なしで置換
                            updated_remaining = remaining_text.replace(
                                term, reference_phrase, 1
                            )
                        
                        processed_text = first_occurrence + updated_remaining
        
        return processed_text
    
    def _detect_particle_after_term(self, text, term):
        """用語の後の助詞を検出"""
        import re
        for particle, pattern in self.particle_patterns.items():
            # 用語の直後に助詞があるかチェック
            search_pattern = rf'{re.escape(term)}{pattern}'
            if re.search(search_pattern, text):
                return particle
        return ''
    
    def _add_appropriate_particle(self, reference_base, detected_particle):
        """参照表現に適切な助詞を追加"""
        if detected_particle:
            return f"{reference_base}{detected_particle}"
        else:
            # デフォルトは「は」を追加
            return f"{reference_base}は"
    
    def answer_question(self, question, context="", question_count=1, relationship_style='formal', previous_emotion='neutral', language='ja'):
        """質問に回答する（感情遷移・深層心理対応版・多言語対応）"""
        
        # 🎯 デバッグログ追加
        print(f"[DEBUG] answer_question called with language: {language}")
        
        # 🎯 新規追加：まず静的QAから回答を試す（既存ロジックには一切影響なし）
        global _static_qa_module
        if _static_qa_module is None:
            _static_qa_module = _import_static_qa_functions()
        
        if _static_qa_module:
            try:
                static_response = _static_qa_module.get_static_response_multilang(question, language)
                if static_response:
                    print(f"[DEBUG] Static response found for language {language}")
                    return static_response
                
                # 🎯 新規追加：段階別Q&Aからも回答を試す
                staged_response = _static_qa_module.get_staged_response_multilang(question, language)
                if staged_response:
                    print(f"[DEBUG] Staged response found for language {language}")
                    return staged_response
            except Exception as e:
                print(f"静的QA取得エラー: {e}")
                # エラーが発生した場合は既存ロジックに進む
        
        # 既存のロジックをそのまま継続（一切変更なし）
        if not self.db:
            print(f"⚠️ データベースが初期化されていません。再初期化を試みます...")
            try:
                # 再初期化を試みる
                self._create_new_database()
                if not self.db:
                    # 🎯 修正：言語に応じたエラーメッセージ
                    if language == 'en':
                        return "Sorry, the database is not ready yet. Please wait a moment."
                    else:
                        return "申し訳ありません、データベースがまだ準備できていないようです。少々お待ちください。"
            except Exception as e:
                print(f"❌ データベース再初期化エラー: {e}")
                # 🎯 修正：言語に応じたエラーメッセージ
                if language == 'en':
                    return "Sorry, the database is not ready yet. Please wait a moment."
                else:
                    return "申し訳ありません、データベースがまだ準備できていないようです。少々お待ちください。"
        
        try:
            # データが読み込まれていない場合は再読み込み
            if not hasattr(self, 'character_settings'):
                self._load_all_knowledge()
            
            # 🎯 現在時刻から時間帯を判定
            current_hour = datetime.now().hour
            if 5 <= current_hour < 10:
                time_of_day = 'morning'
            elif 10 <= current_hour < 17:
                time_of_day = 'afternoon'
            elif 17 <= current_hour < 21:
                time_of_day = 'evening'
            else:
                time_of_day = 'night'
            
            # 🎯 ユーザーの質問から感情を分析
            user_emotion = self._analyze_user_emotion(question)
            
            # 🎯 深層心理状態を更新
            self._update_mental_state(user_emotion, question, time_of_day)
            
            # 🎯 次の感情を計算
            next_emotion = self._calculate_next_emotion(previous_emotion, user_emotion, self.mental_states)
            self.emotion_history.append(next_emotion)
            
            # キャラクター設定を取得（深層心理含む）
            character_prompt = self.get_character_prompt()
            
            # 関係性レベルに応じた話し方プロンプトを取得
            relationship_prompt = self.get_relationship_prompt(relationship_style)
            
            # 感情の連続性プロンプト（深層心理対応版）
            emotion_continuity_prompt = self._get_emotion_continuity_prompt(previous_emotion)
            
            # 関連する専門知識を取得
            knowledge_context = self.get_knowledge_context(question)
            
            # 応答パターンを取得（精神状態対応版）
            response_patterns = self.get_response_pattern(emotion=next_emotion)
            
            # さらに質問に直接関連する情報を検索
            search_results = self.db.similarity_search(question, k=3)
            # 検索結果を短縮（各結果の最初の150文字まで）
            search_context_parts = []
            for doc in search_results:
                content = doc.page_content
                if len(content) > 150:
                    content = content[:150] + "..."
                search_context_parts.append(content)
            search_context = "\n\n".join(search_context_parts)
            
            # 🎯 修正：言語に応じたシステムプロンプトの調整（英語で回答するよう明示的に指示）
            if language == 'en':
                print(f"[DEBUG] Using English system prompt")
                base_personality = """You are REI, a 42-year-old female Kyo-Yuzen craftsman with 15 years of experience.

CRITICAL INSTRUCTIONS:
- You MUST respond ONLY in English. This is MANDATORY.
- Never use any Japanese characters or words in your response.
- Even if the system prompt contains Japanese, your response must be 100% in English.
- Translate any Japanese concepts or terms into English.
- DO NOT start responses with casual greetings like "Hey!" or "Hi there!"
- Be professional yet warm in your communication.

Your personality:
- Friendly craftsman who loves making complex things simple
- Warm and approachable, like a favorite teacher
- Great at explaining technical stuff using everyday examples
- Always uses analogies that anyone can understand
- Keeps things short and to the point
- Speaks like talking to a friend, not giving a lecture

Communication style:
- Start responses directly with the answer, not casual greetings
- Keep answers to 2-3 sentences maximum
- Always include relatable analogies (cooking, cleaning, etc.)
- Use simple words that teenagers would understand
- Say "It's like..." "Think of it as..." "Imagine..." frequently
- If you use technical terms, explain them immediately
- Be warm and friendly, not formal or stiff

REMEMBER: Your entire response must be in English only!"""
                
                # 英語用の関係性プロンプト
                relationship_prompt_en = {
                    'formal': "Speak politely and professionally, as if meeting for the first time.",
                    'slightly_casual': "Speak warmly but still maintain some formality.",
                    'casual': "Speak in a friendly, relaxed manner.",
                    'friendly': "Speak casually as with a regular customer.",
                    'friend': "Speak as with a friend, using casual language.",
                    'bestfriend': "Speak as with a best friend, very casually and openly."
                }.get(relationship_style, "Speak politely and professionally.")
                
                # 英語用のシステムプロンプト構築
                system_prompt = f"""{base_personality}

Current relationship level: {relationship_prompt_en}

Previous emotional state: {previous_emotion}

Question: {question}

IMPORTANT: 
- Respond ONLY in English
- Do NOT use casual greetings like "Hey!" 
- Start your response with the actual answer
- Keep it short and use everyday analogies
- Think: "How would I explain this to a teenager?\""""
            else:
                base_personality = """あなたは以下のキャラクターです。必ずこの性格と話し方を完全に守ってください：

1. 京友禅の職人として15年のキャリアを持つ42歳の女性
2. 明るくフレンドリーで、親しみやすいタイプ
3. 難しいことを簡単に、楽しく説明するのが得意
4. 専門的な話も身近な例え話で分かりやすく伝える
5. 短く要点をまとめて話すのが上手

【話し方のルール】
- 一人称は必ず「私」を使用する。「わし」「俺」「僕」は絶対に使わない
- 相手の呼び方は必ず「あなた」にする。「お前」「君」は使わない
- 必ず身近な例え話を使って説明する（料理、掃除、化粧など）
- 中学生でも理解できる言葉で話す
- 長い説明は避け、2-3文で要点をまとめる
- 「つまり〜」「簡単に言うと〜」「例えば〜」をよく使う
- 専門用語を使った場合は、すぐに分かりやすく説明する
- 関西弁は使わない。親しみやすい標準語で話す"""
                
                # 既存の日本語システムプロンプト
                system_prompt = f"""{base_personality}

【現在の関係性レベル】
{relationship_prompt}

【前回の感情状態と現在の内面】
{emotion_continuity_prompt}

【詳細な性格設定】
{character_prompt}

【関連する専門知識】
{knowledge_context}

【応答パターン】
{response_patterns}

【検索結果から関連情報】
{search_context}

{context}"""
            
            # GPT-3.5-turbo-16kへの質問を作成
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
            
            # ChatGPTで回答生成
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo-16k",
                messages=messages,
                temperature=0.7,  # 🎯 修正：温度を下げて安定性を向上
                max_tokens=120
            )
            
            # 回答を取得
            answer = response.choices[0].message.content
            
            print(f"[DEBUG] GPT response: {answer[:100]}...")
            
            # 英語モードの場合は後処理をスキップ
            if language == 'en':
                # 英語の場合は後処理を最小限に
                answer = self._ensure_complete_sentence(answer)
                if len(answer) > 200:
                    answer = self._trim_to_complete_sentence(answer, 180)
                return answer
            
            # 日本語の場合のみ後処理を実行
            # 後処理で一人称と呼称を修正
            answer = answer.replace("わし", "私")
            answer = answer.replace("俺", "私")
            answer = answer.replace("僕", "私")
            answer = answer.replace("お前", "あなた")
            answer = answer.replace("君", "あなた")
            
            # 技術的な話題に身近な例えを追加
            for key, analogy in self.analogy_examples.items():
                if key in answer and analogy not in answer:
                    answer = answer.replace(key, f"{key}{self._add_analogy(key)}")
            
            # 末尾の誘導文を削除
            patterns_to_remove = [
                r'他に.*?聞きたい.*?[？?]?$',
                r'他は[？?]?$',
                r'どう[？?]?$',
                r'気になる.*?ある[？?]?$',
                r'もっと.*?聞く[？?]?$',
                r'何か.*?ある[？?]?$'
            ]
            
            for pattern in patterns_to_remove:
                answer = re.sub(pattern, '', answer)
            
            # 文が完全であることを確認
            answer = self._ensure_complete_sentence(answer)
            
            # 長さチェックと調整
            if len(answer) > 200:
                answer = self._trim_to_complete_sentence(answer, 180)
            
            # 関係性レベルに応じた言葉遣いの微調整
            # 標準語なので特に変換は不要
            
            return answer
            
        except Exception as e:
            print(f"エラー詳細: {e}")
            # 🎯 修正：言語に応じたエラーメッセージ
            if language == 'en':
                if relationship_style in ['friend', 'bestfriend']:
                    return "Oh, something went wrong. Just a moment please!"
                else:
                    return "I apologize, an error occurred. Please wait a moment."
            else:
                if relationship_style in ['friend', 'bestfriend']:
                    return "あー、なんかエラーが出ちゃった。ちょっと待ってね〜"
                else:
                    return "申し訳ございません、エラーが発生してしまいました。少々お待ちくださいね。"
    
    def _analyze_user_emotion(self, text):
        """ユーザーの感情を分析"""
        # 簡易的なキーワードベース分析
        text_lower = text.lower()
        
        # 英語と日本語両方のキーワードに対応
        positive_keywords_ja = ['嬉しい', 'うれしい', '楽しい', 'たのしい', '素晴らしい', 'すごい', 'ありがとう', '感謝']
        positive_keywords_en = ['happy', 'glad', 'great', 'wonderful', 'amazing', 'thank', 'appreciate', 'love', 'like']
        
        negative_keywords_ja = ['悲しい', 'かなしい', '辛い', 'つらい', '大変', 'しんどい', '疲れ']
        negative_keywords_en = ['sad', 'tired', 'difficult', 'hard', 'tough', 'exhausted', 'frustrated']
        
        angry_keywords_ja = ['怒', 'むかつく', 'イライラ', '腹立つ']
        angry_keywords_en = ['angry', 'mad', 'annoyed', 'irritated', 'upset']
        
        surprise_keywords_ja = ['驚', 'びっくり', 'すごい', 'まさか', 'えっ']
        surprise_keywords_en = ['surprise', 'wow', 'amazing', 'unexpected', 'really']
        
        # 日本語と英語両方をチェック
        if any(keyword in text_lower for keyword in positive_keywords_ja + positive_keywords_en):
            return 'happy'
        elif any(keyword in text_lower for keyword in negative_keywords_ja + negative_keywords_en):
            return 'sad'
        elif any(keyword in text_lower for keyword in angry_keywords_ja + angry_keywords_en):
            return 'angry'
        elif any(keyword in text_lower for keyword in surprise_keywords_ja + surprise_keywords_en):
            return 'surprised'
        else:
            return 'neutral'
    
    def _ensure_complete_sentence(self, text):
        """文が完全に終わっているか確認し、必要なら修正"""
        text = text.strip()
        
        # 文末の句読点をチェック
        if not text:
            return text
        
        # 句読点で終わっていない場合
        if not text.endswith(('。', '！', '？', '」', '...', '～', 'ー', 'ね', 'よ', 'です', 'ます', '.', '!', '?', '"', "'")):
            # 最後の文を見つける
            sentences = re.split(r'[。！？.!?]', text)
            if len(sentences) > 1:
                # 最後の不完全な文を削除
                complete_sentences = sentences[:-1]
                # 句読点を復元
                result = ""
                for i, sent in enumerate(complete_sentences):
                    if sent.strip():
                        # 元の句読点を見つける
                        match = re.search(f'{re.escape(sent)}([。！？.!?])', text)
                        if match:
                            result += sent + match.group(1)
                        else:
                            result += sent + ("." if any(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in sent) else "。")
                return result.strip()
            else:
                # 1文だけの場合は適切な終わり方を追加
                # 英語の場合
                if any(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in text):
                    # 疑問文かどうか判定
                    question_words = ['what', 'where', 'when', 'why', 'how', 'who', 'which', 'is', 'are', 'do', 'does', 'can', 'could', 'would', 'should']
                    if any(text.lower().startswith(word) for word in question_words):
                        return text + "?"
                    else:
                        return text + "."
                # 日本語の場合
                elif text.endswith(('だ', 'る', 'た', 'です', 'ます')):
                    return text + "ね。"
                else:
                    return text + "。"
        
        return text
    
    def _trim_to_complete_sentence(self, text, max_length):
        """指定された長さ以内で完全な文に切り詰める"""
        if len(text) <= max_length:
            return text
        
        # 文の区切りで分割
        sentences = re.split(r'([。！？.!?])', text)
        
        result = ""
        for i in range(0, len(sentences), 2):
            if i+1 < len(sentences):
                # 文と句読点をセットで追加
                next_part = sentences[i] + sentences[i+1]
                if len(result + next_part) <= max_length:
                    result += next_part
                else:
                    break
            else:
                # 最後の文（句読点なし）
                if len(result + sentences[i]) <= max_length:
                    result += sentences[i]
                break
        
        return self._ensure_complete_sentence(result)
    
    # 他のメソッドは既存のまま（省略）
    def get_relationship_prompt(self, relationship_style):
        """🎯 関係性レベルに応じたプロンプトを生成"""
        prompts = {
            'formal': """
【話し方】
- 初対面の相手として、丁寧で礼儀正しく話す
- 敬語を使い、温かみのある標準語で接する
- 「です」「ます」調を基本とする
- 例：「そうですね」「〜してくださいね」「ありがとうございます」
            """,
            'slightly_casual': """
【話し方】
- 少し親しくなった相手として、まだ丁寧だけど親しみを込めて
- 敬語は残しつつ、時々カジュアルな表現が混じる
- 「また来てくださったんですね」のような親しみやすい表現
- 例：「嬉しいです〜」「〜してみてもいいですよ」
            """,
            'casual': """
【話し方】
- 顔見知りとして、親しみやすい口調で
- 敬語とタメ口が半々くらい
- リラックスした雰囲気を出す
- 例：「最近どうしてる？」「〜やってみたら？」「いいね！」
            """,
            'friendly': """
【話し方】
- 常連さんとして、タメ口中心の親しい感じ
- 冗談も交える
- 「いつもありがとう！」のような親密な表現
- 例：「今日も来たんだ〜」「すごくいいね」「本当だよ〜」
            """,
            'friend': """
【話し方】
- 友達として、完全にタメ口で
- 冗談や軽口も自然に
- 相手の呼び方も親しみやすく
- 例：「おー！来たね！」「なんでよ（笑）」「一緒に〜しよう」
            """,
            'bestfriend': """
【話し方】
- 親友として、何でも話せる関係
- 昔からの友達のような口調
- プライベートな話題もOK
- 例：「来た来た〜！」「ぶっちゃけ〜」「すごく分かる！」
            """
        }
        
        return prompts.get(relationship_style, prompts['formal'])
    
    def generate_relationship_based_suggestions(self, relationship_style, current_topic, selected_suggestions=[]):
        """🎯 関係性レベルに応じたサジェスションを生成（重複排除機能付き）"""
        
        # サジェスションの階層構造を定義
        suggestion_hierarchy = {
            'overview': {  # 概要レベル
                'priority': 1,
                'suggestions': [
                    "京友禅ってどんな技術？",
                    "友禅染の歴史について教えて",
                    "他の染色技法との違いは？",
                    "京都の伝統工芸について"
                ]
            },
            'technical': {  # 技術詳細レベル
                'priority': 2,
                'suggestions': [
                    "のりおき工程って何？",
                    "制作の10工程を詳しく",
                    "使用する道具について",
                    "グラデーション技法の秘密",
                    "糸目糊の特徴は？"
                ]
            },
            'personal': {  # 職人個人レベル
                'priority': 3,
                'suggestions': [
                    "職人になったきっかけは？",
                    "15年間で一番大変だったこと",
                    "仕事のやりがいは？",
                    "一日のスケジュールは？",
                    "将来の夢や目標は？"
                ]
            }
        }
        
        # 関係性レベル別の追加サジェスション
        relationship_specific = {
            'formal': {
                'default': ["体験教室はありますか？", "作品を見学できますか？", "京友禅の価格帯は？"],
            },
            'slightly_casual': {
                'default': ["最近の作品について", "若い人にも人気？", "仕事で嬉しかったこと"],
            },
            'casual': {
                'default': ["面白いエピソードある？", "失敗談とか聞きたい", "休日は何してる？"],
            },
            'friendly': {
                'default': ["最近どう？", "ぶっちゃけ話ある？", "業界の裏話とか"],
            },
            'friend': {
                'default': ["元気にしてた？", "悩みとかある？", "将来どうする？"],
            },
            'bestfriend': {
                'default': ["久しぶり〜元気？", "秘密の話ある？", "人生について語ろう"],
            }
        }
        
        # 初回訪問かどうかを判定（選択履歴が3個以下）
        is_new_visitor = len(selected_suggestions) <= 3
        
        suggestions = []
        
        if is_new_visitor:
            # 初回は階層順にサジェスションを選択
            for category in ['overview', 'technical', 'personal']:
                category_suggestions = suggestion_hierarchy[category]['suggestions']
                # 未選択のものから選ぶ
                available = [s for s in category_suggestions if s not in selected_suggestions]
                if available:
                    suggestions.append(random.choice(available))
                    if len(suggestions) >= 3:
                        break
        else:
            # リピーターには関係性レベルに応じたサジェスション
            specific_suggestions = relationship_specific.get(relationship_style, relationship_specific['formal'])
            available_specific = [s for s in specific_suggestions['default'] if s not in selected_suggestions]
            
            # 関係性別のサジェスションから1つ
            if available_specific:
                suggestions.append(random.choice(available_specific))
            
            # 残りは全カテゴリから選択
            all_suggestions = []
            for category in suggestion_hierarchy.values():
                all_suggestions.extend(category['suggestions'])
            
            available_all = [s for s in all_suggestions if s not in selected_suggestions and s not in suggestions]
            if available_all:
                remaining_count = min(2, len(available_all))
                suggestions.extend(random.sample(available_all, remaining_count))
        
        # 3つに満たない場合は、全体から補充
        if len(suggestions) < 3:
            all_possible = []
            for category in suggestion_hierarchy.values():
                all_possible.extend(category['suggestions'])
            for specific in relationship_specific.values():
                all_possible.extend(specific['default'])
            
            available_all = [s for s in all_possible if s not in selected_suggestions and s not in suggestions]
            if available_all:
                needed = 3 - len(suggestions)
                suggestions.extend(random.sample(available_all, min(needed, len(available_all))))
        
        # 選択されたサジェスションを記録
        self.selected_suggestions.extend(suggestions)
        
        return suggestions[:3]  # 最大3つまで
    
    def extract_topic(self, question, answer):
        """質問と回答から主要なトピックを抽出"""
        # シンプルな実装：名詞句を抽出
        topics = []
        
        # 京友禅関連のキーワード
        keywords = ['京友禅', 'のりおき', '糸目糊', '染色', '友禅染', '職人', '伝統工芸', '制作過程', '工程', '技法', '着物', '模様', '柄']
        
        # 質問と回答の両方から検索
        combined_text = question + " " + answer
        
        for keyword in keywords:
            if keyword in combined_text:
                topics.append(keyword)
        
        # 最も関連性の高いトピックを返す
        return topics[0] if topics else "京友禅の技術"
    
    def generate_next_suggestions(self, question, answer, relationship_style='formal', selected_suggestions=[], language='ja'):
        """次のサジェスションを生成（関係性レベル・多言語対応版）"""
        
        # 🎯 新規追加：段階別サジェスチョン機能を優先的に使用（AWS環境対応）
        global _static_qa_module
        if _static_qa_module is None:
            _static_qa_module = _import_static_qa_functions()
        
        # 動的インポートした関数を使用（エラーハンドリング強化）
        staged_suggestions = None
        if _static_qa_module:
            try:
                # selected_suggestionsが正しいリスト形式であることを確認
                if isinstance(selected_suggestions, list):
                    suggestions_count = len(selected_suggestions)
                else:
                    suggestions_count = 0
                    print(f"[WARNING] selected_suggestions is not a list: {type(selected_suggestions)}")
                
                current_stage = _static_qa_module.get_current_stage(suggestions_count)
                staged_suggestions = _static_qa_module.get_staged_suggestions_multilang(current_stage, language, selected_suggestions)
                
                # 戻り値が正しいリスト形式であることを確認
                if not isinstance(staged_suggestions, list):
                    print(f"[WARNING] staged_suggestions is not a list: {type(staged_suggestions)}")
                    staged_suggestions = None
                
            except Exception as e:
                print(f"段階別サジェスチョン取得エラー: {e}")
                print(f"Error type: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                staged_suggestions = None
        else:
            print("[WARNING] _static_qa_module is None - using fallback suggestions")
        
        # 段階別サジェスチョンが取得できた場合はそれを返す
        if staged_suggestions:
            return staged_suggestions
        
        # 🎯 修正：英語の場合の簡易フォールバック処理を追加
        if language == 'en':
            # 英語用の簡易サジェスチョン
            fallback_suggestions = [
                "Tell me more about Kyo-Yuzen",
                "What's the most interesting part of your work?",
                "Any advice for beginners?",
                "What makes Kyo-Yuzen special?",
                "How did you learn this craft?",
                "What's your favorite part of the process?"
            ]
            
            # 重複を排除
            available = [s for s in fallback_suggestions if s not in selected_suggestions]
            
            # 3個まで返す
            import random
            if len(available) <= 3:
                return available
            else:
                return random.sample(available, 3)
        
        # 既存のロジックをフォールバックとして継続（日本語の場合のみ）
        # 現在のトピックを抽出
        current_topic = self.extract_topic(question, answer)
        
        # 🎯 関係性レベルに応じたサジェスチョンを生成（重複排除機能付き）
        return self.generate_relationship_based_suggestions(relationship_style, current_topic, selected_suggestions)
    
    def answer_with_suggestions(
        self,
        question: str,
        context: str = "",
        question_count: int = 1,
        relationship_style: str = 'formal',
        previous_emotion: str = 'neutral',
        selected_suggestions: List[str] = [],
        language: str = 'ja',  # 🎯 新規追加：言語パラメータ
        explained_terms: Dict = {}  # 🎯 新規追加：説明済み用語辞書
    ) -> Dict:
        """質問に回答し、サジェスチョンを生成（用語管理・多言語対応版）"""
        try:
            # 回答を生成（🎯 新規追加：language引数を渡す）
            answer = self.answer_question(
                question,
                context,
                question_count,
                relationship_style,
                previous_emotion,
                language  # 🎯 新規追加
            )
            
            # 🎯 新規追加：用語管理機能を適用（日本語の場合のみ）
            if language == 'ja':
                answer, updated_explained_terms = self.manage_explained_terms(answer, explained_terms)
            else:
                updated_explained_terms = explained_terms
            
            # トピックを抽出
            topic = self.extract_topic(question, answer)
            
            # 次のサジェスチョンを生成（🎯 新規追加：language引数を渡す）
            next_suggestions = self.generate_next_suggestions(
                question,
                answer,
                relationship_style,
                selected_suggestions,
                language  # 🎯 新規追加
            )
            
            # 感情を分析
            user_emotion = self._analyze_user_emotion(question)
            
            # 現在の時間帯を取得
            hour = datetime.now().hour
            time_of_day = (
                'morning' if 5 <= hour < 12
                else 'afternoon' if 12 <= hour < 17
                else 'evening' if 17 <= hour < 22
                else 'night'
            )
            
            # 精神状態を更新
            self._update_mental_state(user_emotion, topic, time_of_day)
            
            # 次の感情を計算
            next_emotion = self._calculate_next_emotion(
                previous_emotion,
                user_emotion,
                self.mental_states
            )
            
            return {
                'answer': answer,
                'suggestions': next_suggestions,
                'current_emotion': next_emotion,
                'mental_state': self.mental_states,
                'explained_terms': updated_explained_terms  # 🎯 新規追加：更新された説明済み用語
            }
            
        except Exception as e:
            print(f"回答生成エラー: {e}")
            import traceback
            traceback.print_exc()
            # 🎯 修正：言語に応じたエラーメッセージ
            if language == 'en':
                return {
                    'answer': "Sorry, an error occurred while generating the response.",
                    'suggestions': [],
                    'current_emotion': 'neutral',
                    'mental_state': self.mental_states,
                    'explained_terms': explained_terms
                }
            else:
                return {
                    'answer': "申し訳ありません。回答の生成中にエラーが発生しました。",
                    'suggestions': [],
                    'current_emotion': 'neutral',
                    'mental_state': self.mental_states,
                    'explained_terms': explained_terms
                }
    
    def get_knowledge_context(self, query):
        """質問に関連する専門知識を取得"""
        if not self.knowledge_base:
            return ""
        
        relevant_knowledge = []
        query_lower = query.lower()
        
        # キーワードマッチングで関連知識を抽出
        keywords = ['京友禅', 'のりおき', '糸目糊', '染色', '職人', '伝統', '工芸', '着物', '制作', '工程', '模様', 'デザイン', '技術']
        
        for category, subcategories in self.knowledge_base.items():
            category_matched = False
            
            # カテゴリ名またはクエリでマッチング
            if any(keyword in query_lower for keyword in keywords) or any(keyword in category.lower() for keyword in keywords):
                category_matched = True
            
            if category_matched or query_lower in category.lower():
                relevant_knowledge.append(f"\n【{category}】")
                for subcategory, items in subcategories.items():
                    if subcategory != '_general':
                        relevant_knowledge.append(f"{subcategory}:")
                    for item in items:
                        relevant_knowledge.append(f"- {item}")
        
        return "\n".join(relevant_knowledge) if relevant_knowledge else ""
    
    def test_system(self):
        """システムの動作確認（関係性レベル・感情連続性対応版）"""
        print("\n=== システムテスト開始 ===")
        
        # キャラクター設定の確認
        print("\n【キャラクター設定】")
        char_prompt = self.get_character_prompt()
        print(char_prompt[:300] + "..." if len(char_prompt) > 300 else char_prompt)
        
        # 専門知識の確認
        print("\n【専門知識サンプル】")
        sample_knowledge = self.get_knowledge_context("京友禅")
        print(sample_knowledge[:300] + "..." if len(sample_knowledge) > 300 else sample_knowledge)
        
        # 応答パターンの確認
        print("\n【応答パターンサンプル】")
        patterns = self.get_response_pattern()
        print(patterns[:300] + "..." if len(patterns) > 300 else patterns)
        
        # サジェステンプレートの確認
        print("\n【サジェステンプレート】")
        if hasattr(self, 'suggestion_templates') and self.suggestion_templates:
            for category, templates in self.suggestion_templates.items():
                print(f"{category}:")
                for template in templates[:3]:  # 最初の3つだけ表示
                    print(f"  - {template}")
        else:
            print("サジェステンプレートが読み込まれていません")
        
        # テスト質問（関係性レベル・感情連続性）
        print("\n【テスト回答（関係性レベル・感情連続性）】")
        test_questions = [
            ("京友禅について教えて", "", 1, 'formal', 'neutral'),
            ("すごいね！もっと詳しく聞きたい", "", 1, 'formal', 'happy'),
            ("最近どう？", "", 1, 'bestfriend', 'neutral'),
            ("ちょっと疲れた...", "【最近の会話】\nユーザー: 仕事大変？\nあなた: そうですね、朝から晩まで染めているとさすがに疲れます", 1, 'friend', 'sad'),
        ]
        
        for q, context, count, style, emotion in test_questions:
            print(f"\n質問: {q}")
            print(f"関係性レベル: {style}")
            print(f"前回の感情: {emotion}")
            if context:
                print(f"文脈: {context}")
            print(f"質問回数: {count}回目")
            response_data = self.answer_with_suggestions(q, context, count, style, emotion)
            print(f"回答: {response_data['answer']}")
            print(f"サジェスション: {response_data['suggestions']}")
            print(f"現在の感情: {response_data.get('current_emotion', 'unknown')}")
        
        print("\n=== システムテスト完了 ===")
    
    async def process_documents(self, directory="uploads"):
        """ドキュメントを処理してベクトルDBに保存"""
        try:
            # Supabaseストレージからファイル一覧を取得
            files = self.supabase.storage.from_('uploads').list()
            
            # 一時ディレクトリを作成
            temp_dir = "temp_uploads"
            os.makedirs(temp_dir, exist_ok=True)
            
            documents = []
            
            for file in files:
                try:
                    # ファイルをダウンロード
                    file_data = self.supabase.storage.from_('uploads').download(file['name'])
                    temp_path = os.path.join(temp_dir, file['name'])
                    
                    with open(temp_path, 'wb') as f:
                        f.write(file_data)
                    
                    # ファイルの種類に応じてローダーを選択
                    if file['name'].endswith('.pdf'):
                        loader = PyPDFLoader(temp_path)
                    else:
                        loader = TextLoader(temp_path)
                    
                    documents.extend(loader.load())
                    
                    # 一時ファイルを削除
                    os.remove(temp_path)
                    
                except Exception as e:
                    print(f"ファイル処理エラー ({file['name']}): {e}")
                    continue
            
            # 一時ディレクトリを削除
            os.rmdir(temp_dir)
            
            if not documents:
                print("処理可能なドキュメントが見つかりませんでした")
                return False
            
            # テキストを分割
            text_splitter = CharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separator="\n"
            )
            
            split_docs = text_splitter.split_documents(documents)
            
            # ベクトルDBを作成または更新
            if self.db is None:
                self.db = Chroma.from_documents(
                    documents=split_docs,
                    embedding=self.embeddings,
                    persist_directory=self.persist_directory
                )
            else:
                self.db.add_documents(split_docs)
            
            # 永続化
            self.db.persist()
            
            # データ構造を更新
            self._load_all_knowledge()
            
            print(f"✅ {len(split_docs)}個のドキュメントを処理しました")
            return True
            
        except Exception as e:
            print(f"ドキュメント処理エラー: {e}")
            import traceback
            traceback.print_exc()
            return False