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
import json
import base64

# --- 봇 설정 값 (환경 변수에서 가져올 거야!) ---
# 이 값은 Koyeb/Replit에서 설정할 DISCORD_TOKEN만 필요해.
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

# 환경 변수가 제대로 설정되었는지 확인
# 로컬에서 첫 실행 시에는 DISCORD_TOKEN이 없을 수 있지만,
# 인증을 위한 client_secret.json 파일은 반드시 있어야 해.
# 만약 DISCORD_TOKEN이 없어도 client_secret.json이 있다면 인증 과정은 진행될 거야.
# 배포 환경에서는 DISCORD_TOKEN이 필수적으로 설정되어야 해.
if not DISCORD_TOKEN:
    print("경고: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다. 로컬 테스트 중이거나 배포 환경에서 설정이 필요합니다.")
    # 로컬에서 첫 인증을 위해 실행할 때는 이 경고가 뜨더라도 계속 진행됩니다.

# --- OAuth 인증 관련 설정 ---
# 인증에 필요한 범위 (유튜브 영상 정보 읽기 전용)
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

# 인증된 유튜브 서비스 객체를 저장할 전역 변수
youtube_service = None

def get_authenticated_service_instance():
    global youtube_service
    if youtube_service: # 이미 인증되어 있다면 기존 서비스 객체 반환
        return youtube_service

    credentials = None
    
    # Replit Secrets에서 token.pickle 파일 내용 가져오기 시도
    token_pickle_base64 = os.environ.get('TOKEN_PICKLE_BASE64')
    if token_pickle_base64:
        try:
            # Base64 디코딩하여 token.pickle 파일 생성 (임시)
            decoded_token = base64.b64decode(token_pickle_base64)
            # 임시 파일로 저장하여 pickle.load가 읽을 수 있도록 함
            with open('temp_token.pickle', 'wb') as f:
                f.write(decoded_token)
            with open('temp_token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            os.remove('temp_token.pickle') # 사용 후 임시 파일 삭제
            print("Secrets에서 token.pickle 정보 불러오기 성공.")
        except Exception as e:
            print(f"Secrets에서 token.pickle 불러오기 오류: {e}. 새로 인증 필요.")
            credentials = None
    
    # 로컬에 token.pickle 파일이 있다면 사용 (로컬 테스트용)
    if not credentials and os.path.exists('token.pickle'):
        print("로컬 token.pickle 파일에서 인증 정보를 불러오는 중...")
        try:
            with open('token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            print("로컬 token.pickle 정보 불러오기 성공.")
        except Exception as e:
            print(f"로컬 token.pickle 로딩 중 오류 발생: {e}. 새로 인증 필요.")
            credentials = None

    # 인증 정보가 없거나 유효하지 않다면 새로 인증 절차 시작 (로컬에서만 가능)
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
                # 임시 파일로 저장하여 InstalledAppFlow가 읽을 수 있도록 함
                with open('temp_client_secret.json', 'w') as f:
                    json.dump(client_secret_data, f)

                flow = InstalledAppFlow.from_client_secrets_file(
                    'temp_client_secret.json', SCOPES)
                print("구글 계정으로 로그인하여 봇에게 권한을 허용해주세요.")
                
                # Replit 환경에서는 웹 브라우저가 직접 열리지 않으므로, 이 부분은 로컬에서만 작동합니다.
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
                
                os.remove('temp_client_secret.json') # 사용 후 임시 파일 삭제
                os.remove('token.pickle') # 사용 후 임시 파일 삭제

            except FileNotFoundError as e:
                print(f"인증 파일 오류: {e}. 프로그램 종료.")
                exit(1)
            except Exception as e:
                print(f"인증 과정 중 오류 발생: {e}")
                print("client_secret.json 내용이 올바른지 확인해주세요.")
                raise # 오류 발생 시 프로그램 종료

    youtube_service = build('youtube', 'v3', credentials=credentials)
    return youtube_service

# --- 유튜브 링크에서 비디오 ID 추출 함수 ---
def extract_video_id(url):
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=|)([a-zA-Z0-9_-]{11})'
    )
    match = re.match(youtube_regex, url)
    if match:
        return match.group(6)
    return None

# --- Flask Health Check (봇을 24시간 돌릴 때 필요해!) ---
app = Flask(__name__)

@app.route('/healthz')
def healthz():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

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

    # 디스코드 봇 객체 정의 (client.run() 호출 전에 정의되어야 함)
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    # --- 디스코드 봇 이벤트 ---
    @client.event
    async def on_ready():
        print(f'로그인 성공! 봇 이름: {client.user}')
        print('봇이 온라인 상태가 되었어요! 이제 유튜브 링크를 기다릴게! 🔗')

        # 봇이 준비되면 Flask Health Check 서버를 백그라운드에서 실행!
        flask_thread = Thread(target=run_flask)
        flask_thread.start()
        print(f"Flask Health Check 서버 시작됨 (Port: {os.environ.get('PORT', 8080)})")

    @client.event
    async def on_message(message):
        if message.author == client.user: # 봇 자신이 보낸 메시지는 무시!
            return

        # 봇에게 인사하기!
        if message.content == '!안녕':
            await message.channel.send('안녕! 만나서 반가워! 😊')
            return

        # 유튜브 링크 분석 명령어
        if message.content.startswith('!링크'):
            parts = message.content.split(' ', 1)
            if len(parts) < 2:
                await message.channel.send("유튜브 링크를 알려줘! (예: `!링크 https://www.youtube.com/watch?v=xxxxxxxxxxx`)")
                return

            youtube_url = parts[1]
            video_id = extract_video_id(youtube_url)

            if not video_id:
                await message.channel.send("유효한 유튜브 링크를 찾을 수 없어. 다시 확인해 줄래?")
                return

            await message.channel.send(f"링크 분석 중... 잠시만 기다려 줘! 🕵️‍♀️")

            try:
                # 인증된 유튜브 서비스 객체 사용
                current_youtube_service = get_authenticated_service_instance() # 항상 최신 인증 정보로 서비스 가져오기
                video_response = current_youtube_service.videos().list(
                    part='snippet,liveStreamingDetails',
                    id=video_id
                ).execute()

                if not video_response['items']:
                    await message.channel.send("해당 영상 정보를 찾을 수 없어. 링크가 정확한지 확인해 줘.")
                    return

                video_data = video_response['items'][0]
                snippet = video_data.get('snippet', {})
                live_details = video_data.get('liveStreamingDetails', {})

                title = snippet.get('title', '제목 없음')

                if 'actualStartTime' in live_details and 'actualEndTime' in live_details:
                    start_time_iso = live_details['actualStartTime']
                    end_time_iso = live_details['actualEndTime']

                    start_dt_utc = datetime.datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
                    end_dt_utc = datetime.datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))

                    kst_tz = pytz.timezone('Asia/Seoul')
                    start_dt_kst = start_dt_utc.astimezone(kst_tz)
                    end_dt_kst = end_dt_utc.astimezone(kst_tz)

                    duration = end_dt_utc - start_dt_utc
                    total_seconds = int(duration.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60

                    response_message = (
                        f"**🔗 영상 제목:** {title}\n"
                        f"**📅 날짜:** {start_dt_kst.strftime('%m/%d')}\n"
                        f"**⏰ 방송 시작:** {start_dt_kst.strftime('%H:%M')}\n"
                        f"**⏱️ 방송 종료:** {end_dt_kst.strftime('%H:%M')}\n"
                        f"**⏳ 총 방송 시간:** {hours}시간 {minutes}분 {seconds}초"
                    )
                elif 'scheduledStartTime' in live_details and 'actualStartTime' not in live_details:
                    response_message = (
                        f"'{title}' 영상은 아직 시작하지 않은 라이브 방송이거나, 현재 진행 중인 라이브 방송이야. 😅\n"
                        f"방송이 종료된 후에 다시 링크를 알려주면 정확한 시간을 알려줄 수 있어!"
                    )
                elif 'actualStartTime' in live_details and 'actualEndTime' not in live_details:
                    response_message = (
                        f"'{title}' 영상은 현재 진행 중인 라이브 방송이야! 🤩\n"
                        f"방송이 종료된 후에 다시 링크를 알려주면 총 방송 시간을 계산해 줄게!"
                    )
                else:
                    response_message = (
                        f"'{title}' 영상은 라이브 스트리밍 정보가 없거나, 일반 영상인 것 같아. 😥\n"
                        f"라이브 방송이었는지 다시 한번 확인해 줄래?"
                    )

                await message.channel.send(response_message)

            except Exception as e:
                print(f"링크 처리 중 오류 발생: {e}")
                await message.channel.send(f"링크 처리 중 문제가 발생했어! ㅠㅠ 오류 내용: `{e}`")

    # 디스코드 봇을 실행!
    client.run(DISCORD_TOKEN)
