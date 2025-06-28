import discord
import datetime
import asyncio
import os
import re
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from flask import Flask
from threading import Thread
import pytz
import json # JSON 파일 내용을 다루기 위해 추가
import base64 # Base64 인코딩된 토큰을 다루기 위해 추가

# ... (기존 DISCORD_TOKEN 설정 부분) ...

# --- OAuth 인증 관련 설정 ---
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

youtube_service = None

def get_authenticated_service_instance():
    global youtube_service
    if youtube_service:
        return youtube_service

    credentials = None
    
    # Replit Secrets에서 token.pickle 파일 내용 가져오기
    token_pickle_base64 = os.environ.get('TOKEN_PICKLE_BASE64')
    if token_pickle_base64:
        try:
            # Base64 디코딩하여 token.pickle 파일 생성 (임시)
            decoded_token = base64.b64decode(token_pickle_base64)
            with open('temp_token.pickle', 'wb') as f: # 임시 파일로 저장
                f.write(decoded_token)
            with open('temp_token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            os.remove('temp_token.pickle') # 사용 후 임시 파일 삭제
            print("Secrets에서 token.pickle 정보 불러오기 성공.")
        except Exception as e:
            print(f"Secrets에서 token.pickle 불러오기 오류: {e}. 새로 인증 필요.")
            credentials = None
    
    # 기존 token.pickle 파일이 로컬에 있다면 사용 (로컬 테스트용)
    if not credentials and os.path.exists('token.pickle'):
        print("로컬 token.pickle 파일에서 인증 정보를 불러오는 중...")
        try:
            with open('token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            print("로컬 token.pickle 정보 불러오기 성공.")
        except Exception as e:
            print(f"로컬 token.pickle 로딩 중 오류 발생: {e}. 새로 인증 필요.")
            credentials = None

    # 인증 정보가 없거나 유효하지 않다면 새로 인증 절차 시작
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("인증 토큰 만료, 새로고침 중...")
            credentials.refresh(Request())
            # 새로고침된 토큰을 Secrets에 다시 저장 (이 부분은 Replit에서 직접 업데이트 필요)
            # 또는 로컬에서 다시 실행하여 token.pickle을 업데이트하고 Base64로 변환하여 Secrets 업데이트
            print("토큰 새로고침됨. Secrets 업데이트가 필요할 수 있습니다.")
        else:
            print("새로운 인증 필요. 웹 브라우저가 열릴 겁니다. (로컬에서만 가능)")
            # Replit Secrets에서 client_secret.json 내용 가져오기
            client_secret_json_str = os.environ.get('CLIENT_SECRET_JSON')
            if not client_secret_json_str:
                print("오류: CLIENT_SECRET_JSON 환경 변수가 설정되지 않았습니다. Replit Secrets에 추가해주세요.")
                raise FileNotFoundError("CLIENT_SECRET_JSON secret 없음")

            try:
                # Secrets 내용을 임시 client_secret.json 파일로 저장
                client_secret_data = json.loads(client_secret_json_str)
                with open('temp_client_secret.json', 'w') as f:
                    json.dump(client_secret_data, f)

                flow = InstalledAppFlow.from_client_secrets_file(
                    'temp_client_secret.json', SCOPES)
                print("구글 계정으로 로그인하여 봇에게 권한을 허용해주세요.")
                # Replit에서는 웹 브라우저가 직접 열리지 않으므로, 이 부분은 로컬에서만 작동합니다.
                # Replit에서는 이미 token.pickle이 Secrets에 있어야 합니다.
                if os.environ.get('REPL_ID'): # Replit 환경인지 확인
                     print("Replit 환경에서는 초기 인증이 불가능합니다. token.pickle을 Secrets에 직접 넣어주세요.")
                     raise Exception("Replit에서 초기 인증 불가")
                
                credentials = flow.run_local_server(port=0)
                
                # 새로 생성된 token.pickle을 Base64로 인코딩하여 출력
                with open('token.pickle', 'wb') as token_file:
                    pickle.dump(credentials, token_file)
                with open('token.pickle', 'rb') as token_file:
                    encoded_token = base64.b64encode(token_file.read()).decode('utf-8')
                print("\n\n--- 새로운 TOKEN_PICKLE_BASE64 값 ---")
                print(encoded_token)
                print("-------------------------------------\n\n")
                print("이 값을 Replit Secrets의 TOKEN_PICKLE_BASE64에 업데이트 해주세요.")
                
                os.remove('temp_client_secret.json') # 임시 파일 삭제
                os.remove('token.pickle') # 임시 파일 삭제

            except FileNotFoundError as e:
                print(f"인증 파일 오류: {e}. 프로그램 종료.")
                exit(1)
            except Exception as e:
                print(f"인증 과정 중 오류 발생: {e}")
                print("client_secret.json 내용이 올바른지 확인해주세요.")
                raise # 오류 발생 시 프로그램 종료

    youtube_service = build('youtube', 'v3', credentials=credentials)
    return youtube_service

# ... (나머지 봇 코드 - extract_video_id, discord events, Flask health check 등은 그대로) ...

# --- 봇 실행의 시작점 ---
if __name__ == '__main__':
    # 봇 시작 시 유튜브 API 서비스 인증을 한 번만 수행
    try:
        # Replit 환경에서는 초기 인증을 건너뛰고 Secrets에서 바로 불러오도록 합니다.
        if os.environ.get('REPL_ID') and not os.environ.get('TOKEN_PICKLE_BASE64'):
            print("Replit 환경입니다. TOKEN_PICKLE_BASE64 Secrets가 설정되어 있어야 합니다.")
            print("로컬에서 먼저 인증을 완료하고 token.pickle을 Secrets에 넣어주세요.")
            exit(1) # Replit에서 token.pickle 없으면 종료

        get_authenticated_service_instance()
        print("유튜브 API 서비스 초기화 완료.")
    except Exception as e:
        print(f"유튜브 API 서비스 초기화 실패: {e}")
        print("client_secret.json 내용이 올바른지, token.pickle이 Secrets에 잘 설정되었는지 확인해주세요.")
        exit(1)

    client.run(DISCORD_TOKEN)
