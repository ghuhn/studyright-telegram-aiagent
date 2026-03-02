import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# If modifying these scopes, delete the file token.json.
# We only need read-only access to Gmail (not sending).
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    """Shows basic usage of the Gmail API.
    Logs the user in and generates token.json for the bot.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("=================================================================")
                print("ERROR: credentials.json not found!")
                print("Please download it from the Google Cloud Console and place it")
                print("in this folder.")
                print("=================================================================")
                return
                
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080, bind_addr='127.0.0.1')
            
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    print("=================================================================")
    print("SUCCESS! token.json has been generated.")
    print("The Study Bot can now securely access your Gmail account.")
    print("=================================================================")

if __name__ == '__main__':
    main()
