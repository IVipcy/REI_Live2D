# modules/coe_font_client.py
# -*- coding: utf-8 -*-
import os
import hmac
import hashlib
import json
import requests
import base64
from datetime import datetime, timezone
from typing import Optional

class CoeFontClient:
    def __init__(self):
        """CoeFontクライアントの初期化"""
        self.access_key = os.getenv('COEFONT_ACCESS_KEY')
        self.access_secret = os.getenv('COEFONT_ACCESS_SECRET')
        self.coefont_id = os.getenv('COEFONT_VOICE_ID')
        self.api_base_url = 'https://api.coefont.cloud/v2'
        
        # 設定チェック
        if not all([self.access_key, self.access_secret, self.coefont_id]):
            print("Warning: CoeFont configuration is incomplete. Please check environment variables.")
            print(f"COEFONT_ACCESS_KEY: {'✓' if self.access_key else '✗'}")
            print(f"COEFONT_ACCESS_SECRET: {'✓' if self.access_secret else '✗'}")
            print(f"COEFONT_VOICE_ID: {'✓' if self.coefont_id else '✗'}")
    
    def is_available(self) -> bool:
        """CoeFont設定が利用可能かチェック"""
        return all([self.access_key, self.access_secret, self.coefont_id])
    
    def _get_timestamp(self) -> str:
        """UNIX時間(UTC)を文字列で取得"""
        # CoeFont公式サンプルと完全一致
        return str(int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()))
    
    def _generate_signature(self, timestamp: str, request_body: str) -> str:
        """
        HMAC-SHA256署名を生成（公式ドキュメント準拠）
        
        Args:
            timestamp: UNIX時間(UTC)の文字列
            request_body: JSONエンコードされたリクエストボディ
            
        Returns:
            HEX形式の署名文字列
        """
        # タイムスタンプとリクエストボディを結合（公式サンプルと完全一致）
        message = timestamp + request_body
        
        # デバッグ用ログ
        print(f"[DEBUG] Timestamp: {timestamp}")
        print(f"[DEBUG] Request body: {request_body}")
        print(f"[DEBUG] Combined message for signature: {message}")
        print(f"[DEBUG] Access secret (first 10 chars): {self.access_secret[:10]}...")
        
        # HMAC-SHA256で署名を生成（公式サンプルと完全一致）
        signature = hmac.new(
            bytes(self.access_secret, 'utf-8'), 
            message.encode('utf-8'), 
            hashlib.sha256
        ).hexdigest()
        
        print(f"[DEBUG] Generated signature: {signature[:20]}...")
        
        return signature

    def _get_emotion_params(self, emotion: Optional[str]) -> dict:
        """感情に応じた音声パラメータを取得（CoeFont API公式仕様対応版）"""
        # デフォルトパラメータ（CoeFont API公式ドキュメントに基づく）
        default_params = {
            'speed': 1.0,       # 速度（0.1-10.0の範囲）
            'pitch': 0,         # ピッチ（-3000〜3000の範囲、±1200で1オクターブ）
            'volume': 1.0,      # 音量（0.2-2.0の範囲）
            'kuten': 0.5,       # 句点の間隔（0-5秒の範囲）
            'toten': 0.3        # 読点の間隔（0.2-2.0秒の範囲、省略可能）
        }
        
        if not emotion:
            return default_params
        
        # 感情別パラメータ（API制限内で調整）
        emotion_params = {
            'happy': {
                'speed': 1.1,         # わずかに速く
                'pitch': 150,         # 約1.5半音上（明るく）
                'volume': 1.1,        # 少し大きめ
                'kuten': 0.4,         # 句点間隔短めに
                'toten': 0.2          # 読点間隔短めに
            },
            'sad': {
                'speed': 1.1,         # わずかに速く
                'pitch': 150,         # 約1.5半音上（明るく）
                'volume': 1.1,        # 少し大きめ
                'kuten': 0.4,         # 句点間隔短めに
                'toten': 0.2          # 読点間隔短めに
            },
            'angry': {
                'speed': 1.1,         # わずかに速く
                'pitch': 150,         # 約1.5半音上（明るく）
                'volume': 1.1,        # 少し大きめ
                'kuten': 0.4,         # 句点間隔短めに
                'toten': 0.2          # 読点間隔短めに
            },
            'surprised': {
                'speed': 1.1,         # わずかに速く
                'pitch': 150,         # 約1.5半音上（明るく）
                'volume': 1.1,        # 少し大きめ
                'kuten': 0.4,         # 句点間隔短めに
                'toten': 0.2          # 読点間隔短めに
            },
            'neutral': {
                'speed': 1.1,         # わずかに速く
                'pitch': 150,         # 約1.5半音上（明るく）
                'volume': 1.1,        # 少し大きめ
                'kuten': 0.4,         # 句点間隔短めに
                'toten': 0.2          # 読点間隔短めに
            }
        }
        return emotion_params.get(emotion, default_params)

    def test_connection(self) -> bool:
        """
        接続テスト（公式ドキュメント準拠）
        
        Returns:
            接続成功時True、失敗時False
        """
        print("Testing CoeFont connection...")
        
        if not self.is_available():
            print("CoeFont configuration is incomplete")
            return False
        
        try:
            # APIキーの一部を表示（セキュリティのため一部マスク）
            print(f"Using API key: {self.access_key[:10]}...")
            print(f"Using CoeFont ID: {self.coefont_id}")
            
            # 公式ドキュメントに基づく最小限のリクエストデータ
            request_data = {
                'coefont': self.coefont_id,
                'text': 'これはテストです。',
                'format': 'wav'  # 公式ドキュメントで必須パラメータ
            }
            
            # JSONエンコード（公式ドキュメントに基づく）
            request_body = json.dumps(request_data)
            print(f"Request body: {request_body}")
            
            # タイムスタンプ生成
            timestamp = self._get_timestamp()
            print(f"Timestamp: {timestamp}")
            
            # 署名生成（公式ドキュメントに基づく）
            signature = self._generate_signature(timestamp, request_body)
            
            # ヘッダー設定（公式ドキュメントに完全準拠）
            headers = {
                'Content-Type': 'application/json',
                'Authorization': self.access_key,
                'X-Coefont-Date': timestamp,
                'X-Coefont-Content': signature
            }
            
            print("Sending request to CoeFont API...")
            print(f"URL: {self.api_base_url}/text2speech")
            print(f"Headers: {json.dumps({k: v[:20] + '...' if k in ['Authorization', 'X-Coefont-Content'] and len(v) > 20 else v for k, v in headers.items()}, indent=2)}")
            
            # API呼び出し
            response = requests.post(
                f"{self.api_base_url}/text2speech",
                data=request_body.encode('utf-8'),  # UTF-8でエンコード
                headers=headers,
                timeout=30
            )
            
            print(f"CoeFont API response: HTTP {response.status_code}")
            
            if response.status_code == 200:
                print("CoeFont connection test successful")
                return True
            elif response.status_code == 302:
                print("CoeFont connection test successful (redirect)")
                return True
            else:
                print(f"CoeFont API error: HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"Error detail: {error_detail}")
                except:
                    print(f"Error detail: {response.text}")
                return False
                
        except Exception as e:
            print(f"CoeFont connection error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def generate_audio(self, text: str, emotion: Optional[str] = None) -> Optional[str]:
        """
        テキストから音声を生成（公式ドキュメント完全準拠）
        
        Args:
            text: 音声生成するテキスト
            emotion: 感情（オプション）
            
        Returns:
            音声データ（Base64エンコード済みdata URL）、失敗時None
        """
        if not self.is_available():
            print("❌ CoeFont設定が不完全です")
            return None
        
        try:
            print(f"🎵 CoeFont API呼び出し中... (テキスト: {text[:30]}... 感情: {emotion})")
            
            # 基本のリクエストデータ（公式ドキュメント準拠）
            request_data = {
                'coefont': self.coefont_id,
                'text': text,
                'format': 'wav'  # 必須パラメータ
            }
            
            # 感情パラメータを追加（ある場合）
            if emotion:
                emotion_params = self._get_emotion_params(emotion)
                request_data.update(emotion_params)
                print(f"🎭 感情パラメータ適用: {emotion_params}")
            
            # JSONエンコード
            request_body = json.dumps(request_data)
            
            # タイムスタンプ生成
            timestamp = self._get_timestamp()
            
            # 署名生成
            signature = self._generate_signature(timestamp, request_body)
            
            # ヘッダー設定（公式ドキュメント準拠）
            headers = {
                'Content-Type': 'application/json',
                'Authorization': self.access_key,
                'X-Coefont-Date': timestamp,
                'X-Coefont-Content': signature
            }
            
            # API呼び出し
            response = requests.post(
                f"{self.api_base_url}/text2speech",
                data=request_body.encode('utf-8'),  # UTF-8でエンコード
                headers=headers,
                timeout=60
            )
            
            print(f"📡 CoeFont APIレスポンス: HTTP {response.status_code}")
            
            if response.status_code == 200:
                # 直接音声データが返ってきた場合
                audio_data = response.content
                print(f"✅ CoeFont音声生成成功: [audio_data {len(audio_data)} bytes]")
                
                # Base64エンコードしてdata URLとして返す
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                return f"data:audio/wav;base64,{audio_base64}"
                
            elif response.status_code == 302:
                # リダイレクトの場合（公式ドキュメント通り）
                redirect_url = response.headers.get('Location')
                if redirect_url:
                    print(f"📎 リダイレクトURL取得: {redirect_url}")
                    
                    # リダイレクト先から音声データを取得
                    audio_response = requests.get(redirect_url, timeout=60)
                    if audio_response.status_code == 200:
                        audio_data = audio_response.content
                        print(f"✅ CoeFont音声生成成功: [audio_data {len(audio_data)} bytes]")
                        
                        # Base64エンコードしてdata URLとして返す
                        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                        return f"data:audio/wav;base64,{audio_base64}"
                    else:
                        print(f"❌ リダイレクト先でエラー: HTTP {audio_response.status_code}")
                        return None
                else:
                    print("❌ リダイレクトURLが見つかりません")
                    return None
            else:
                print(f"❌ CoeFont APIエラー: HTTP {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"エラー詳細: {error_detail}")
                except:
                    print(f"エラー詳細: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ CoeFont音声生成エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_available_coefonts(self) -> Optional[list]:
        """利用可能なCoeFont一覧を取得"""
        if not self.is_available():
            print("❌ CoeFont設定が不完全です")
            return None
        
        try:
            print("📋 CoeFont一覧取得中...")
            
            timestamp = self._get_timestamp()
            signature = hmac.new(
                self.access_secret.encode('utf-8'),
                timestamp.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': self.access_key,
                'X-Coefont-Date': timestamp,
                'X-Coefont-Content': signature
            }
            
            response = requests.get(
                f"{self.api_base_url}/coefonts/pro",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                coefonts = response.json()
                print(f"✅ CoeFont一覧取得成功: {len(coefonts)} 個の音声")
                return coefonts
            else:
                print(f"❌ CoeFont一覧取得エラー: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ CoeFont一覧取得エラー: {e}")
            return None


# 使用例とテスト用コード
if __name__ == "__main__":
    # テスト実行
    client = CoeFontClient()
    
    if client.is_available():
        print("✅ CoeFont設定確認: OK")
        
        # 接続テスト
        if client.test_connection():
            print("✅ 接続テスト: 成功")
            
            # 音声一覧表示
            client.print_voice_list()
            
            # 感情パラメータテスト
            client.test_emotion_params()
        else:
            print("❌ 接続テスト: 失敗")
    else:
        print("❌ CoeFont設定確認: 失敗 - 環境変数を設定してください")