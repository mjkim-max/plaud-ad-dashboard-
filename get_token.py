from google_auth_oauthlib.flow import InstalledAppFlow

def get_refresh_token():
    # 1. 구글 애즈 권한 범위 설정
    scopes = ["https://www.googleapis.com/auth/adwords"]

    print("="*50)
    print("구글 클라우드에서 받은 ID와 Secret을 입력해주세요.")
    print("="*50)

    # 2. 사용자에게 직접 입력받기 (파일 만들기 귀찮으니까)
    client_id = input("1. Client ID를 붙여넣고 엔터: ").strip()
    client_secret = input("2. Client Secret을 붙여넣고 엔터: ").strip()

    # 3. 설정 딕셔너리 생성
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    # 4. 인증 실행 (브라우저가 열립니다)
    app_flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    
    # 로컬 서버를 띄워서 인증 진행
    creds = app_flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    print("\n" + "="*50)
    print("🎉 성공! 아래 Refresh Token을 복사하세요:")
    print("="*50)
    print(creds.refresh_token)
    print("="*50)

if __name__ == "__main__":
    get_refresh_token()
