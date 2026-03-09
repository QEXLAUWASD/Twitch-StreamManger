import requests


class TwitchClient:
    def __init__(self, client_id: str, access_token: str, streamer_id: str):
        self.streamer_id = streamer_id
        self.api_url = "https://api.twitch.tv/helix/channels"
        self.headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def update_stream_category(self, category: str) -> None:
        try:
            game_search_url = "https://api.twitch.tv/helix/games"
            params = {"name": category}
            response = requests.get(game_search_url, headers=self.headers, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data["data"]:
                    game_id = data["data"][0]["id"]
                    game_name = data["data"][0]["name"]
                    url = f"{self.api_url}?broadcaster_id={self.streamer_id}"
                    payload = {"game_id": game_id}
                    response = requests.patch(url, headers=self.headers, json=payload, timeout=10)
                    if response.status_code == 204:
                        print(f"Stream category updated to: {game_name}")
                    else:
                        print(f"Failed to update stream category: {response.status_code}")
                else:
                    print(f"Game category '{category}' not found on Twitch")
                    if category != "Just Chatting":
                        self.update_stream_category("Just Chatting")
            else:
                print(f"Failed to search for game: {response.status_code}")
        except Exception as e:
            print(f"Error updating category: {e}")

    def update_stream_title(self, title: str) -> None:
        try:
            url = f"{self.api_url}?broadcaster_id={self.streamer_id}"
            payload = {"title": title}
            response = requests.patch(url, headers=self.headers, json=payload, timeout=10)
            if response.status_code == 204:
                print(f"Stream title updated to: {title}")
            else:
                print(f"Failed to update stream title: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error updating title: {e}")


def format_title(template: str, game: str) -> str:
    import time

    current_date = time.strftime("%Y-%m-%d")
    return template.replace("%date%", current_date).replace("%game%", game)
