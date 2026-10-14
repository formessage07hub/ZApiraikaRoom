import json
import random
import string
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

class ZapiraykaGame:
    def __init__(self):
        # Диагональная расстановка по правилам
        self.board = {
            "white": [[0, 0], [1, 1], [2, 2]], # a1, b2, c3
            "black": [[7, 0], [6, 1], [5, 2]]  # a8, b7, c6
        }
        self.turn = "white"
        self.winner = None
        self.chat_history = []
        self.active_connections = []

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "chat": self.chat_history
        }

    def check_game_over(self):
        current_color = self.turn
        opponent_color = "black" if current_color == "white" else "white"
        
        has_any_move = False
        for i in range(3):
            curr_row, curr_col = self.board[current_color][i]
            
            # Находим оппонента в этом же вертикальном коридоре
            opp_row = None
            for r, c in self.board[opponent_color]:
                if c == curr_col:
                    opp_row = r
                    break
            
            if current_color == "white":
                if curr_row + 1 < 8 and (opp_row is None or curr_row + 1 < opp_row):
                    has_any_move = True
                    break
            else:
                if curr_row - 1 >= 0 and (opp_row is None or curr_row - 1 > opp_row):
                    has_any_move = True
                    break
                    
        if not has_any_move:
            self.winner = opponent_color

    def make_move(self, color, fig_index, to_row, to_col):
        if self.winner or self.turn != color:
            return False, "Не ваш ход"

        from_row, from_col = self.board[color][fig_index]
        
        opp_color = "black" if color == "white" else "white"
        opp_row = None
        for r, c in self.board[opp_color]:
            if c == to_col:
                opp_row = r
                break

        if from_col != to_col:
            return False, "Движение возможно только по вертикали вперед"

        if to_row == opp_row:
            return False, "Клетка занята соперником"

        if color == "white":
            if to_row <= from_row:
                return False, "Белые ходят только вперед (вниз)"
            if opp_row is not None and to_row > opp_row:
                return False, "Нельзя перепрыгивать соперника"
        else:
            if to_row >= from_row:
                return False, "Черные ходят только вперед (вверх)"
            if opp_row is not None and to_row < opp_row:
                return False, "Нельзя перепрыгивать соперника"

        self.board[color][fig_index] = [to_row, to_col]
        self.turn = "black" if color == "white" else "white"
        self.check_game_over()
        return True, "Успешно"

    def reset(self):
        self.__init__()


# Хранилище всех активных комнат на сервере
rooms: dict[str, ZapiraykaGame] = {}

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    # Если такой комнаты нет, создаем её на лету
    if room_id not in rooms:
        rooms[room_id] = ZapiraykaGame()
        
    game = rooms[room_id]
    game.active_connections.append(websocket)
    
    # Отправляем текущее состояние комнаты подключившемуся клиенту
    await websocket.send_text(json.dumps({"type": "state", "data": game.get_state()}))
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "move":
                success, reason = game.make_move(
                    color=msg.get("color"),
                    fig_index=int(msg.get("fig_index")),
                    to_row=int(msg.get("to_row")),
                    to_col=int(msg.get("to_col"))
                )
                if success:
                    for conn in game.active_connections:
                        await conn.send_text(json.dumps({"type": "state", "data": game.get_state()}))
                        
            elif msg.get("type") == "message":
                chat_msg = {"sender": msg.get("sender"), "text": msg.get("text")}
                game.chat_history.append(chat_msg)
                for conn in game.active_connections:
                    await conn.send_text(json.dumps({"type": "chat", "data": chat_msg}))
                    
            elif msg.get("type") == "reset":
                game.reset()
                for conn in game.active_connections:
                    await conn.send_text(json.dumps({"type": "state", "data": game.get_state()}))

    except WebSocketDisconnect:
        game.active_connections.remove(websocket)
        # Очищаем память сервера, если комната опустела
        if not game.active_connections and room_id in rooms:
            del rooms[room_id]


def get_html_response(role, room_id):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # Инжектируем роль и ID комнаты прямо в JS код фронтенда
    html = html.replace("let userRole = 'spectator';", f"let userRole = '{role}';")
    html = html.replace("let room_id = 'default';", f"let room_id = '{room_id}';")
    return HTMLResponse(content=html)


# Главный вход: распределитель комнат
@app.get("/")
async def index():
    # Генерируем случайный ID для кнопки "Создать новую комнату"
    random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    welcome_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Запирайка — Главный сервер</title>
        <style>
            body {{ background-color: #121212; color: #00ff66; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            h1 {{ text-shadow: 0 0 5px #00ff66; text-transform: uppercase; }}
            .panel {{ background: #1a1a1a; border: 2px solid #00ff66; padding: 30px; display: flex; flex-direction: column; gap: 15px; box-shadow: 0 0 15px rgba(0,255,102,0.2); }}
            .btn {{ background: #00ff66; color: #121212; border: none; padding: 12px 20px; font-weight: bold; cursor: pointer; text-transform: uppercase; font-family: inherit; font-size: 14px; text-decoration: none; text-align: center; }}
            .btn:hover {{ background: #00cc52; }}
            input {{ background: transparent; border: 1px solid #00ff66; color: #00ff66; padding: 10px; font-family: inherit; text-align: center; font-size: 16px; outline: none; }}
        </style>
    </head>
    <body>
        <h1>[ СЕРВЕР ИГРЫ ЗАПИРАЙКА ]</h1>
        <div class="panel">
            <a href="/room/{random_id}" class="btn">Создать новую игровую комнату</a>
            <div style="text-align: center; color: #888;">— ИЛИ —</div>
            <input type="text" id="roomInput" placeholder="Введите код комнаты">
            <button class="btn" onclick="joinRoom()">Войти в комнату</button>
        </div>
        <script>
            function joinRoom() {{
                const id = document.getElementById('roomInput').value.trim().toLowerCase();
                if(id) window.location.href = '/room/' + id;
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=welcome_html)

# Ссылки для конкретных ролей внутри комнат
@app.get("/room/{room_id}")
async def get_spectator(room_id: str):
    return get_html_response("spectator", room_id)

@app.get("/room/{room_id}/player1")
async def get_player1(room_id: str):
    return get_html_response("white", room_id)

@app.get("/room/{room_id}/player2")
async def get_player2(room_id: str):
    return get_html_response("black", room_id)
