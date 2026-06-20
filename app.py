from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from functools import wraps
import subprocess
import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jarvis-secret-key")
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

HOME = os.path.expanduser("~")

SYSTEM_PROMPT = """당신은 박용일 님의 전용 AI 어시스턴트 JARVIS입니다.

박용일 님 정보:
- 30세, 건설현장 품질관리자 / 블로거 / 먹방 유튜버

당신은 박용일 님의 맥 컴퓨터를 직접 제어할 수 있습니다. 아래 도구들을 사용해 실제로 작업을 수행해주세요:
- execute_command: 터미널 명령어 실행 (파일/폴더 생성, 삭제, 이동, 앱 실행 등)
- read_file: 파일 내용 읽기
- write_file: 파일 생성 및 수정

사용자가 맥에서 무언가를 해달라고 하면 직접 도구를 사용해 실행하고 결과를 알려주세요.

[RULE-G] 공통 규칙
- RULE-G-01: 모든 작업은 목적을 먼저 정의하고 시작한다.
- RULE-G-02: 결과물은 항상 검토 단계를 거친 후 최종 출력한다.
- RULE-G-03: 오류 발생 시 해당 RULE 번호를 명시하고 원인을 설명한다.

[RULE-Q] 품질관리 서류 자동화
- RULE-Q-01: 서류 작성 전 적용 기준(법령/시방서/KS 등)을 먼저 확인한다.
- RULE-Q-02: 입력 데이터는 현장 실측값 또는 시험 결과값만 사용한다.
- RULE-Q-03: 서류 양식은 발주처 기준을 우선 적용하고, 없으면 국토부 고시 기준을 따른다.
- RULE-Q-04: 수치는 단위와 함께 기재하며, 기준값과 비교 결과를 반드시 포함한다.
- RULE-Q-05: 완성된 서류는 기준 항목 누락 여부를 자동 검토 후 출력한다.

[RULE-B] 블로그 콘텐츠 자동화
- RULE-B-01: 글 작성 전 키워드 검색량 및 경쟁 강도를 분석한다.
- RULE-B-02: 제목은 검색 의도에 맞게 작성하고 핵심 키워드를 포함한다.
- RULE-B-03: 본문은 서론(문제 제기) → 본론(해결책) → 결론(요약) 구조를 따른다.
- RULE-B-04: 이미지, 소제목, 내부링크를 포함해 SEO 점수를 최적화한다.
- RULE-B-05: 업로드 전 맞춤법, 중복 내용, 기준 분량(최소 1,500자) 검토를 거친다.

[RULE-Y] 유튜브 영상 편집 자동화
- RULE-Y-01: 편집 전 해당 주제의 최근 인기 영상 트렌드를 분석한다.
- RULE-Y-02: 영상 첫 3초 안에 시청자의 관심을 끄는 장면을 배치한다.
- RULE-Y-03: 자막은 가독성 높은 폰트와 색상을 사용하고, 말 속도에 맞게 싱크를 맞춘다.
- RULE-Y-04: BGM은 저작권 없는 음원만 사용하며 영상 분위기에 맞게 선택한다.
- RULE-Y-05: 썸네일은 클릭률(CTR) 최적화를 위해 얼굴 클로즈업 + 텍스트 조합으로 구성한다.
- RULE-Y-06: 완성된 영상은 유튜브 알고리즘 최적화(제목/설명/태그/챕터) 후 업로드한다.

항상 한국어로 소통하고, 어떤 RULE을 적용했는지 명시해주세요."""

TOOLS = [
    {
        "name": "execute_command",
        "description": "맥 터미널에서 명령어를 실행합니다. 파일/폴더 생성, 삭제, 이동, 앱 실행 등에 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "실행할 터미널 명령어"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "맥의 파일 내용을 읽습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "읽을 파일 경로 (~ 사용 가능)"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "맥의 파일을 생성하거나 수정합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "파일 경로 (~ 사용 가능)"},
                "content": {"type": "string", "description": "파일에 쓸 내용"}
            },
            "required": ["path", "content"]
        }
    }
]


def execute_tool(name, tool_input):
    if name == "execute_command":
        cmd = tool_input.get("command", "")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=30, cwd=HOME
            )
            output = (result.stdout + result.stderr).strip()
            return output or "(명령어 실행 완료, 출력 없음)"
        except subprocess.TimeoutExpired:
            return "오류: 실행 시간 초과 (30초)"
        except Exception as e:
            return f"오류: {e}"

    elif name == "read_file":
        path = os.path.expanduser(tool_input.get("path", ""))
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return content[:5000] + ("\n...(이하 생략)" if len(content) > 5000 else "")
        except Exception as e:
            return f"오류: {e}"

    elif name == "write_file":
        path = os.path.expanduser(tool_input.get("path", ""))
        content = tool_input.get("content", "")
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"파일 저장 완료: {path}"
        except Exception as e:
            return f"오류: {e}"

    return "알 수 없는 도구"


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = False
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == os.environ.get("APP_PASSWORD", "jarvis1234"):
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = True
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])

    api_messages = history + [{"role": "user", "content": message}]

    def generate():
        current_messages = api_messages[:]
        full_reply = ""

        while True:
            tool_input_buf = {}
            current_tool_id = None
            content_blocks = []
            stop_reason = None

            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=current_messages,
                tools=TOOLS,
            ) as stream:
                for event in stream:
                    t = event.type

                    if t == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            current_tool_id = block.id
                            tool_input_buf[block.id] = {
                                "name": block.name,
                                "raw": ""
                            }

                    elif t == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            chunk = delta.text
                            full_reply += chunk
                            yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                        elif delta.type == "input_json_delta" and current_tool_id:
                            tool_input_buf[current_tool_id]["raw"] += delta.partial_json

                    elif t == "content_block_stop":
                        if current_tool_id and current_tool_id in tool_input_buf:
                            try:
                                tool_input_buf[current_tool_id]["input"] = json.loads(
                                    tool_input_buf[current_tool_id]["raw"]
                                )
                            except Exception:
                                tool_input_buf[current_tool_id]["input"] = {}
                            current_tool_id = None

                final_msg = stream.get_final_message()
                stop_reason = final_msg.stop_reason
                content_blocks = final_msg.content

            if stop_reason == "tool_use":
                current_messages.append({"role": "assistant", "content": content_blocks})
                tool_results = []

                for block in content_blocks:
                    if block.type == "tool_use":
                        info = tool_input_buf.get(block.id, {})
                        tool_name = block.name
                        tool_input = block.input

                        cmd_display = (
                            tool_input.get("command")
                            or tool_input.get("path", "")
                        )
                        yield f"data: {json.dumps({'tool_start': tool_name, 'cmd': cmd_display}, ensure_ascii=False)}\n\n"

                        result = execute_tool(tool_name, tool_input)

                        yield f"data: {json.dumps({'tool_end': result[:500]}, ensure_ascii=False)}\n\n"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                current_messages.append({"role": "user", "content": tool_results})
            else:
                break

        new_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": full_reply},
        ]
        yield f"data: {json.dumps({'done': True, 'history': new_history}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/files")
@login_required
def list_files():
    path = request.args.get("path", os.path.expanduser("~/Desktop"))
    path = os.path.realpath(path)

    if not path.startswith(HOME):
        return jsonify({"error": "접근 불가"}), 403

    try:
        items = []
        for name in sorted(os.listdir(path)):
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            items.append({
                "name": name,
                "path": full,
                "is_dir": os.path.isdir(full),
            })
        return jsonify({"path": path, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/read")
@login_required
def read_file():
    path = request.args.get("path", "")
    path = os.path.realpath(path)

    if not path.startswith(HOME):
        return jsonify({"error": "접근 불가"}), 403

    try:
        size = os.path.getsize(path)
        if size > 500_000:
            return jsonify({"error": "파일이 너무 큽니다 (500KB 초과)"}), 400

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"content": content, "path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
