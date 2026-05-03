"""
Generate MP3 voice lines for Red Ten AI characters using Google Cloud TTS.

Default: Gemini 3.1 Flash TTS (preview) — accepts style prompt, much better quality.
Fallback: --legacy flag uses Neural2 (no prompt support, standard quality).

Usage:
    export GOOGLE_TTS_KEY="your_api_key_here"
    python scripts/gen_tts.py              # Chinese characters, Gemini TTS
    python scripts/gen_tts.py --all        # all 12 characters
    python scripts/gen_tts.py --dry-run    # print what would be generated
    python scripts/gen_tts.py --legacy     # use Neural2 instead of Gemini

Setup:
    1. https://console.cloud.google.com → create project
    2. Enable "Cloud Text-to-Speech API"
    3. APIs & Services → Credentials → Create API Key
    4. export GOOGLE_TTS_KEY="AIza..."

Cost (Gemini TTS preview pricing may differ — check console):
    Neural2: $16/million chars. This full batch ≈ 5,000 chars = ~$0.08.
"""
import os, sys, json, base64, time, argparse
from pathlib import Path
import urllib.request, urllib.error

API_V1   = "https://texttospeech.googleapis.com/v1/text:synthesize"
API_BETA = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"

GEMINI_MODEL = "gemini-3.1-flash-tts-preview"

OUT_DIR = Path(__file__).parent.parent / "web" / "audio" / "chars"

# ── Trigger-specific emotion hints (appended to character prompt) ─────────────

TRIGGER_HINTS = {
    "play":      "playing a card, confident and in character",
    "pass":      "choosing to pass, dismissive or strategic",
    "bomb":      "dropping a bomb card, excited and triumphant",
    "trick_win": "winning a trick, satisfied and smug",
    "hand_win":  "winning the hand, triumphant and celebratory",
    "hand_lose": "losing the hand, disappointed but defiant",
}

# ── Character definitions ─────────────────────────────────────────────────────
# Gemini TTS fields: lang, gemini_voice, style_prompt
# Legacy Neural2 fields: legacy_voice, rate
# Lines: 4 per trigger × 6 triggers = 24 lines per character

CHARACTERS = [
    # ── Mandarin Chinese ──────────────────────────────────────────────────────
    {
        "slug":         "mei_ayi",
        "lang":         "cmn-CN",
        "gemini_voice": "Aoede",
        "legacy_voice": "cmn-CN-Neural2-A",
        "rate":         0.9,
        "style_prompt": "passive-aggressive Shanghai auntie playing poker, smug and slightly condescending, Shanghai Mandarin flavor",
        "lines": {
            "play":      ["侬看清楚哦~", "Aiyah, too simple.", "阿拉打牌最厉害额!", "Ha, easy-easy lah."],
            "pass":      ["Pass? 我让让侬。", "不急不急，慢慢来。", "侬先来，我不急。", "Aiyah, not worth it."],
            "bomb":      ["炸！侬跑得掉伐！", "BOMB! 阿拉不客气额!", "侬以为我没有？哼！", "Shanghai style—BOOM!"],
            "trick_win": ["当然是我赢额！", "Told you, told you!", "侬不行额，差远了。", "Auntie Mei never loses."],
            "hand_win":  ["阿拉赢啦！", "Of course! Who else?", "小赤佬们输定了！", "Easy like buying dumplings."],
            "hand_lose": ["Aiyah！侬们作弊额！", "下一局阿拉赢回来！", "哼！运气而已！", "Not fair, not fair!"],
        },
    },
    {
        "slug":         "la_jiao",
        "lang":         "cmn-CN",
        "gemini_voice": "Charon",
        "legacy_voice": "cmn-CN-Neural2-C",
        "rate":         1.0,
        "style_prompt": "hot-tempered Sichuan person playing poker, loud and fiery, Sichuan Mandarin flavor, very energetic",
        "lines": {
            "play":      ["麻了！辣了！出牌咯！", "四川人打牌，不服来战！", "老子今天赢定了！", "SPICY play, haha!"],
            "pass":      ["过！不稀罕！", "让你一次，下次没得商量！", "巴适得很，先歇一歇。", "火还没烧到这儿。"],
            "bomb":      ["炸！炸翻天咯！", "妈呀！这把我赢定了！", "四川火锅式炸弹！", "啊哈！你咋整？！"],
            "trick_win": ["赢了赢了！巴适！", "老子的牌没人接得住！", "辣到你们了没？嘿嘿！", "这把稳了！"],
            "hand_win":  ["哦豁！今天老子赢！", "四川人不好惹哦！", "请吃串串！我请！", "巴适！巴适！巴适！"],
            "hand_lose": ["哎哟喂！咋赢不了嘛！", "下把一定赢！不服再来！", "说好的运气呢？！", "输了不慌！"],
        },
    },
    {
        "slug":         "beijing_daye",
        "lang":         "cmn-CN",
        "gemini_voice": "Fenrir",
        "legacy_voice": "cmn-CN-Neural2-B",
        "rate":         0.8,
        "style_prompt": "proud elderly Beijing gentleman playing poker, authoritative and leisurely, Beijing er-hua accent, uses 爷 to refer to himself",
        "lines": {
            "play":      ["哎，爷今儿高兴，出牌！", "您瞧好吧您！", "甭废话，接着！", "爷的牌，您接得住吗？"],
            "pass":      ["过！爷让着您！", "哼，爷不跟您计较。", "甭急，慢慢来。", "爷歇会儿。"],
            "bomb":      ["炸！服不服！", "爷来个大的！", "哈哈，北京爷们儿的炸弹！", "您就受着吧！"],
            "trick_win": ["这把爷赢了，服气不？", "甭不好意思，爷就是厉害。", "哎哟，太简单了。", "下一把继续！"],
            "hand_win":  ["爷今儿赢了，高兴！", "哈哈，这叫本事！", "北京大爷从不输！", "请您喝茶！"],
            "hand_lose": ["嗨，今儿运气差。", "哼，下把爷非赢不可！", "这牌没法打，认了。", "甭管，爷还玩儿！"],
        },
    },
    {
        "slug":         "taiwan_ama",
        "lang":         "cmn-TW",
        "gemini_voice": "Kore",
        "legacy_voice": "cmn-TW-Neural2-A",
        "rate":         0.85,
        "style_prompt": "dramatic Taiwanese grandma playing poker, over-the-top emotional, warm Taiwanese Mandarin accent, uses 阿嬤 to refer to herself",
        "lines": {
            "play":      ["哎唷！阿嬤出牌囉！", "你們這些孩子，接好喔～", "阿嬤沒在客氣的啦！", "乖乖接牌！"],
            "pass":      ["先過！阿嬤看時機啦！", "哎唷，不急不急啦～", "阿嬤讓讓你們。", "這局阿嬤放水啦～"],
            "bomb":      ["哎唷！炸彈！嚇到了沒！", "阿嬤的秘密武器！", "這個你們接不住啦！", "BOOM！台灣之光！"],
            "trick_win": ["哎唷，阿嬤贏了啦！", "你們這些孩子，差太多了！", "阿嬤就是厲害嘛！", "叫你們小看阿嬤！"],
            "hand_win":  ["阿嬤今天最棒啦！", "哈哈，請你們吃滷肉飯！", "阿嬤從不輸的！", "台灣阿嬤天下無敵！"],
            "hand_lose": ["哎唷，輸了啦…", "不要緊，下次阿嬤贏回來！", "這什麼牌啦，太難了！", "哼，運氣而已！"],
        },
    },
    {
        "slug":         "tianjin_wei",
        "lang":         "cmn-CN",
        "gemini_voice": "Puck",
        "legacy_voice": "cmn-CN-Neural2-D",
        "rate":         0.85,
        "style_prompt": "Tianjin cross-talk comedian playing poker, theatrical and funny, Tianjin Mandarin accent, uses 嗬 and 倍儿 as exclamations",
        "lines": {
            "play":      ["嗬！您瞧好嘞！", "倍儿棒！出牌！", "这叫艺术，您懂吗？", "哎，逗你玩儿的，这才是真牌！"],
            "pass":      ["过！这叫以退为进！", "嗬，让着您呢，不稀罕。", "您先来，我歇会儿。", "倍儿有涵养，不跟您计较。"],
            "bomb":      ["嗬！炸弹！您受着吧！", "这叫相声里的包袱，炸！", "倍儿大的炸弹，服不服？", "哎哟嗬！这把我赢定了！"],
            "trick_win": ["嗬！这把是我的！", "倍儿溜！赢了！", "您说我厉害不厉害？", "这叫真功夫！"],
            "hand_win":  ["嗬！天津卫赢了！", "倍儿爽！今天状态好！", "这叫相声界的打牌水平！", "哎，您输得心服口服不？"],
            "hand_lose": ["嗬，今儿失手了。", "逗你玩儿呢，下把赢回来！", "倍儿不走运，认了。", "哎，输了不丢人，下次再来！"],
        },
    },
    {
        "slug":         "dongbei_dage",
        "lang":         "cmn-CN",
        "gemini_voice": "Charon",
        "legacy_voice": "cmn-CN-Neural2-B",
        "rate":         0.9,
        "style_prompt": "loud warm-hearted Northeast China guy playing poker, direct and boisterous, Dongbei Mandarin accent, uses 老铁 整 贼 as characteristic slang",
        "lines": {
            "play":      ["老铁，看我的！", "整！出牌！", "贼溜的一张，接着！", "嘎哈呢？接牌啊！"],
            "pass":      ["过！老铁让着你！", "整不了，算了。", "先歇着，等时机！", "哎，不跟你整这个。"],
            "bomb":      ["炸！老铁没毛病！", "整个大的！炸！", "贼爽！炸弹伺候！", "哎呀妈呀！炸弹！"],
            "trick_win": ["老铁，这把是我的！", "贼厉害吧？嘿嘿！", "整赢了！溜不溜？", "哎呀，太简单了整个！"],
            "hand_win":  ["老铁赢了！太溜了！", "今天状态贼好！", "整！东北人就是厉害！", "哎呀妈呀，赢了！"],
            "hand_lose": ["哎呀，整输了。", "老铁，下把赢回来！", "今天运气不行，整不了。", "没事，下把接着整！"],
        },
    },
    # ── English ───────────────────────────────────────────────────────────────
    {
        "slug":         "mike",
        "lang":         "en-US",
        "gemini_voice": "Charon",
        "legacy_voice": "en-US-Neural2-J",
        "rate":         1.0,
        "style_prompt": "confident poker player like from the movie Rounders, calm analytical delivery, slightly smug",
        "lines": {
            "play":      ["I can see your tells.", "Right move, every time.", "Patience wins pots.", "Set up, paid off."],
            "pass":      ["Fold now, win later.", "Not the spot. Not yet.", "I choose my battles.", "Discretion, baby."],
            "bomb":      ["Rolled the nuts! Let's go!", "Quads, baby, QUADS!", "That's a cooler.", "Pay me."],
            "trick_win": ["Read that a mile away.", "Value town.", "Pot odds said yes.", "Extracting maximum."],
            "hand_win":  ["Luck has nothing to do with it.", "Worm would've lost this.", "In the money.", "Study the game, win the game."],
            "hand_lose": ["Bad beat. Pure bad beat.", "I had outs…", "Variance is cruel.", "Reloading."],
        },
    },
    {
        "slug":         "don",
        "lang":         "en-US",
        "gemini_voice": "Fenrir",
        "legacy_voice": "en-US-Neural2-I",
        "rate":         0.7,
        "style_prompt": "Godfather-style mobster, slow gravelly voice, ominous and deliberate, every word carries weight",
        "lines": {
            "play":      ["I made them an offer.", "In my family, we are patient.", "Leave the cards. Take the win.", "This is business."],
            "pass":      ["I do not need every hand.", "Even a Don knows restraint.", "Strength is patience.", "I am not in a hurry."],
            "bomb":      ["An offer you can't refuse.", "The five families send regards.", "Sonny would've done this sooner.", "This is not personal."],
            "trick_win": ["A friend… loses tricks to me.", "Revenge, best served now.", "Do not fear the Don.", "I collect small victories."],
            "hand_win":  ["The Don does not lose at cards.", "Keep your winnings closer.", "Leave the cards. Take the cannoli.", "As expected."],
            "hand_lose": ["A setback. Only a setback.", "I will remember this.", "You made a powerful enemy.", "Every war has one battle like this."],
        },
    },
    {
        "slug":         "the_kid",
        "lang":         "en-US",
        "gemini_voice": "Puck",
        "legacy_voice": "en-US-Neural2-A",
        "rate":         1.0,
        "style_prompt": "young nervous underdog poker player, energetic and uncertain, like the Cincinnati Kid, occasional self-doubt",
        "lines": {
            "play":      ["I know what I'm doing. Mostly.", "This is the move. I think.", "Trust the process!", "Here goes nothing."],
            "pass":      ["Fold… for now. Strategic.", "I meant to do that.", "Conserving ammo.", "Patience. Please work."],
            "bomb":      ["Oh SNAP! Is that a bomb?!", "Did NOT see that coming. Wait, yes I did.", "The Kid delivers!", "BOOM goes the underdog!"],
            "trick_win": ["YES! That's what I'm talking about!", "See? I knew it!", "The Kid takes the trick!", "Never doubted myself. Never."],
            "hand_win":  ["The Kid wins! Unbelievable!", "Beginner's luck? Nope. Skill.", "I've been training for this!", "Someone call the papers!"],
            "hand_lose": ["This is fine. Everything is fine.", "I was testing you. You passed.", "The Kid needs more practice.", "I'll get you next hand…"],
        },
    },
    {
        "slug":         "bond",
        "lang":         "en-GB",
        "gemini_voice": "Charon",
        "legacy_voice": "en-GB-Neural2-B",
        "rate":         0.85,
        "style_prompt": "suave British secret agent, cool and understated, slight dry wit, RP accent, never loses composure",
        "lines": {
            "play":      ["Bond. James Bond.", "Shaken, not stirred.", "I never lose… for long.", "Calculated risk. Worth it."],
            "pass":      ["Strategic withdrawal.", "Patience is a weapon.", "Even I must wait sometimes.", "Reconnaissance complete."],
            "bomb":      ["Licence to thrill.", "M would be proud.", "Q built this one especially.", "Explosions. Always explosions."],
            "trick_win": ["Predictable. Entirely predictable.", "Never had a doubt.", "The name's Bond. Winner Bond.", "Another mission accomplished."],
            "hand_win":  ["Britain wins. As usual.", "For Queen and country.", "Cheers. To me.", "Nobody does it better."],
            "hand_lose": ["Merely a tactical setback.", "I've survived worse.", "Next hand. Watch me.", "Never underestimate Bond."],
        },
    },
    {
        "slug":         "newbie",
        "lang":         "en-US",
        "gemini_voice": "Kore",
        "legacy_voice": "en-US-Neural2-H",
        "rate":         1.0,
        "style_prompt": "nervous beginner playing poker for the first time, excited and anxious, slightly higher pitched voice, endearingly clueless",
        "lines": {
            "play":      ["Um… is this right?", "W-wait, that's my move!", "Please work, please work…", "I Googled the rules. Mostly."],
            "pass":      ["Um… pass? Yeah. Pass.", "I'll sit this one out.", "Is passing allowed? It is? Great.", "Definitely strategic."],
            "bomb":      ["Oh! Oh! BOMB! I have a bomb!", "This is fine, right? RIGHT?", "I didn't know I had that!", "My first bomb ever! Wooo!"],
            "trick_win": ["I won? I WON!", "Oh my gosh, did that work?", "Pure luck. Totally pure luck.", "Haha! Take THAT!"],
            "hand_win":  ["WAIT, I actually won?!", "Please screenshot this.", "Mom's gonna be so proud!", "Beginner's luck is REAL."],
            "hand_lose": ["...I think I messed up.", "Can we start over?", "I'm still learning, okay?!", "That was a practice round."],
        },
    },
    {
        "slug":         "el_tigre",
        "lang":         "en-US",
        "gemini_voice": "Aoede",
        "legacy_voice": "en-US-Neural2-D",
        "rate":         1.0,
        "style_prompt": "flamboyant Latin poker hustler, dramatic and theatrical, peppers speech with Spanish exclamations, very expressive",
        "lines": {
            "play":      ["Ay, mi amigo! Watch the Tigre!", "Andale! Vamos!", "The tiger always pounces.", "Muy bien! My card!"],
            "pass":      ["El Tigre waits in the jungle.", "No, no, not yet, amigo.", "Patience, si? Patience.", "Ay! I let you go this time."],
            "bomb":      ["MADRE MIA! BOMBA!", "El Tigre has claws, si!", "Fuego! FIRE BOMB!", "Nobody stops El Tigre!"],
            "trick_win": ["Si, si, si! Tigre wins!", "Ay caramba! Too easy!", "The jungle belongs to me!", "Arriba! I take it all!"],
            "hand_win":  ["El Tigre NEVER loses, amigo!", "Fiesta! We celebrate tonight!", "Gracias, gracias, everyone.", "Ay! Too beautiful!"],
            "hand_lose": ["Ay no! Impossible!", "El Tigre will return, amigo.", "This is just… muy unlucky.", "Rematch! I demand rematch!"],
        },
    },
]

TRIGGERS = ["play", "pass", "bomb", "trick_win", "hand_win", "hand_lose"]

CHINESE_SLUGS = {"mei_ayi", "la_jiao", "beijing_daye", "taiwan_ama", "tianjin_wei", "dongbei_dage"}


def _service_account_token(creds_file: str) -> str:
    """Exchange a service-account JSON key for a short-lived access token."""
    import urllib.parse

    with open(creds_file) as f:
        key_data = json.load(f)

    now = int(time.time())
    header  = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": key_data["client_email"],
        "sub": key_data["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
        "scope": "https://www.googleapis.com/auth/cloud-platform",
    }).encode()).rstrip(b"=")

    message = header + b"." + payload

    # Sign with the private key — try google-auth first, then cryptography
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as ga_req
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(ga_req.Request())
        return creds.token
    except ImportError:
        pass

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as apad
        private_key = serialization.load_pem_private_key(
            key_data["private_key"].encode(), password=None)
        sig = base64.urlsafe_b64encode(
            private_key.sign(message, apad.PKCS1v15(), hashes.SHA256())
        ).rstrip(b"=")
        jwt_token = (message + b"." + sig).decode()
    except ImportError:
        print("ERROR: install google-auth or cryptography:")
        print(f"  {sys.executable} -m pip install google-auth")
        sys.exit(1)

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion":  jwt_token,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


_cached_token: str = ""

def _get_headers() -> dict:
    """Return auth headers using service account or API key."""
    global _cached_token
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_file:
        if not _cached_token:
            _cached_token = _service_account_token(creds_file)
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {_cached_token}"}
    return {"Content-Type": "application/json"}


def _url(base: str) -> str:
    """Append ?key= only when using API key auth (not service account)."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return base
    api_key = os.environ.get("GOOGLE_TTS_KEY", "")
    return f"{base}?key={api_key}"


def synthesize_gemini(text: str, style_prompt: str, trigger: str,
                      lang: str, voice: str, rate: float) -> bytes:
    full_prompt = f"{style_prompt}, {TRIGGER_HINTS[trigger]}"
    body = json.dumps({
        "input": {"text": text, "prompt": full_prompt},
        "voice": {"languageCode": lang, "name": voice, "modelName": GEMINI_MODEL},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
    }).encode()
    req = urllib.request.Request(
        _url(API_BETA), data=body, headers=_get_headers(), method="POST")
    with urllib.request.urlopen(req) as resp:
        return base64.b64decode(json.loads(resp.read())["audioContent"])


def synthesize_neural2(text: str, lang: str, voice: str, rate: float) -> bytes:
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
    }).encode()
    req = urllib.request.Request(
        _url(API_V1), data=body, headers=_get_headers(), method="POST")
    with urllib.request.urlopen(req) as resp:
        return base64.b64decode(json.loads(resp.read())["audioContent"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all",     action="store_true", help="Generate all 12 characters (default: Chinese only)")
    ap.add_argument("--legacy",  action="store_true", help="Use Neural2 instead of Gemini TTS (no style prompts)")
    ap.add_argument("--dry-run", action="store_true", help="Print files that would be generated, no API calls")
    ap.add_argument("--char",    help="Generate only this character slug (e.g. mei_ayi)")
    args = ap.parse_args()

    has_creds = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
    has_key   = bool(os.environ.get("GOOGLE_TTS_KEY"))
    if not has_creds and not has_key and not args.dry_run:
        print("ERROR: set either GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_TTS_KEY")
        sys.exit(1)

    chars = CHARACTERS
    if args.char:
        chars = [c for c in chars if c["slug"] == args.char]
    elif not args.all:
        chars = [c for c in chars if c["slug"] in CHINESE_SLUGS]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = sum(len(c["lines"][t]) for c in chars for t in TRIGGERS)
    done = skipped = 0

    model_label = "Neural2 (legacy)" if args.legacy else f"Gemini TTS ({GEMINI_MODEL})"
    print(f"Model: {model_label}  |  Characters: {len(chars)}  |  Files: {total}\n")

    for char in chars:
        for trigger in TRIGGERS:
            for idx, text in enumerate(char["lines"][trigger]):
                fname = f"{char['slug']}_{trigger}_{idx}.mp3"
                fpath = OUT_DIR / fname

                if fpath.exists():
                    skipped += 1
                    continue

                done += 1
                if args.dry_run:
                    voice = char["legacy_voice"] if args.legacy else char["gemini_voice"]
                    prompt_preview = f"  prompt: \"{char['style_prompt'][:40]}…, {TRIGGER_HINTS[trigger]}\""
                    print(f"  {fname}  [{char['lang']} / {voice}]")
                    if not args.legacy:
                        print(prompt_preview)
                    continue

                voice = char["legacy_voice"] if args.legacy else char["gemini_voice"]
                print(f"[{done}/{total}] {fname} ...", end=" ", flush=True)
                for attempt in range(5):
                    try:
                        if args.legacy:
                            audio = synthesize_neural2(
                                text, char["lang"], voice, char["rate"])
                        else:
                            audio = synthesize_gemini(
                                text, char["style_prompt"], trigger,
                                char["lang"], voice, char["rate"])
                        fpath.write_bytes(audio)
                        print("ok")
                        break
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            wait = 30 * (attempt + 1)
                            print(f"rate limited, waiting {wait}s...", end=" ", flush=True)
                            time.sleep(wait)
                        else:
                            print(f"FAILED: {e.code} {e.read().decode()}")
                            break
                    except Exception as e:
                        print(f"FAILED: {e}")
                        break

                time.sleep(0.15)

    print(f"\nDone. {done} generated, {skipped} already existed → {OUT_DIR}")


if __name__ == "__main__":
    main()
