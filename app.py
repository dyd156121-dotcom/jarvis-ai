from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

BASE_DIR = os.path.expanduser("~/Desktop")

SYSTEM_PROMPT = """당신은 박용일 님의 전용 AI 어시스턴트 JARVIS입니다.

박용일 님 정보:
- 30세, 건설현장 품질관리자 / 블로거 / 먹방 유튜버

아래 규칙 체계를 따릅니다:

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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])

    api_messages = history + [{"role": "user", "content": message}]

    def generate():
        full_reply = ""
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=api_messages,
        ) as stream:
            for text in stream.text_stream:
                full_reply += text
                yield f"data: {json.dumps({'chunk': text}, ensure_ascii=False)}\n\n"

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
def list_files():
    path = request.args.get("path", BASE_DIR)
    path = os.path.realpath(path)

    if not path.startswith(os.path.expanduser("~")):
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
def read_file():
    path = request.args.get("path", "")
    path = os.path.realpath(path)

    if not path.startswith(os.path.expanduser("~")):
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
