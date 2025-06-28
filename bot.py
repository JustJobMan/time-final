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
    # 이전에 인증 정보를 저장한 파일(token.pickle)이 있는지 확인
    if os.path.exists('token.pickle'):
        print("token.pickle 파일에서 인증 정보를 불러오는 중...")
        try:
            with open('token.pickle', 'rb') as token:
                credentials = pickle.load(token)
            if credentials and credentials.valid:
                print("인증 정보 유효함.")
            elif credentials and credentials.expired and credentials.refresh_token:
                print("인증 토큰 만료, 새로고침 중...")
                credentials.refresh(Request())
                with open('token.pickle', 'wb') as token: # 새로고침된 토큰 저장
                    pickle.dump(credentials, token)
                print("인증 정보 새로고침 및 저장 완료.")
            else:
                print("token.pickle 파일이 유효하지 않거나 만료됨. 새로 인증 필요.")
                credentials = None
        except Exception as e:
            print(f"token.pickle 파일 로딩 중 오류 발생: {e}. 새로 인증 필요.")
            credentials = None

    # 인증 정보가 없거나 유효하지 않다면 새로 인증 절차 시작
    if not credentials:
        print("새로운 인증 필요. 웹 브라우저가 열릴 겁니다.")
        try:
            # client_secret.json 파일에서 인증 정보를 가져와서 Flow 객체 생성
            if not os.path.exists('client_secret.json'):
                print("오류: client_secret.json 파일이 현재 폴더에 없습니다.")
                print("Google Cloud Platform에서 다운로드하여 봇 파일과 같은 폴더에 넣어주세요.")
                raise FileNotFoundError("client_secret.json 파일 없음")

            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            print("구글 계정으로 로그인하여 봇에게 권한을 허용해주세요.")
            credentials = flow.run_local_server(port=0) # port=0은 사용 가능한 포트를 자동으로 찾음
            # 얻어온 인증 정보를 파일에 저장하여 다음 실행 시 재사용
            with open('token.pickle', 'wb') as token:
                pickle.dump(credentials, token)
            print("새로운 인증 정보가 token.pickle에 저장되었습니다.")
        except FileNotFoundError as e:
            print(f"인증 파일 오류: {e}. 프로그램 종료.")
            exit(1)
        except Exception as e:
            print(f"인증 과정 중 오류 발생: {e}")
            print("client_secret.json 파일이 올바른지, Google Cloud 설정이 정확한지 확인해주세요.")
            raise # 오류 발생 시 프로그램 종료

    # 인증된 자격 증명으로 유튜브 API 서비스 빌드
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

# --- 디스코드 봇 설정 ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- Flask Health Check (봇을 24시간 돌릴 때 필요해!) ---
app = Flask(__name__)

@app.route('/healthz')
def healthz():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

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
    if message.author == client.user:
        return

    if message.content == '!안녕':
        await message.channel.send('안녕! 만나서 반가워! 😊')
        return

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

# --- 봇 실행의 시작점 ---
if __name__ == '__main__':
    # 봇 시작 시 유튜브 API 서비스 인증을 한 번만 수행
    # 이 부분이 client_secret.json을 찾고, 웹 브라우저를 띄워 인증을 진행합니다.
    try:
        get_authenticated_service_instance()
        print("유튜브 API 서비스 초기화 완료.")
    except Exception as e:
        print(f"유튜브 API 서비스 초기화 실패: {e}")
        print("client_secret.json 파일이 올바른지, 첫 인증을 완료했는지 확인해주세요.")
        exit(1)

    # 디스코드 봇을 실행!
    client.run(DISCORD_TOKEN)
