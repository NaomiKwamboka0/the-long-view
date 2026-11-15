"""Speak every line of an episode, measure it, and write plan-<ep>.json and voice-<ep>.wav.

    python script.py teachers
    python script.py parents

A line is "text" or ("text", seconds): the seconds are the least time the picture needs
(typing, a page opening) before the next line may start.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

VOICE, SPEED, SR = "af_heart", 1.0, 24000
LEAD, GAP, TAIL = 0.8, 0.45, 1.0
# How the voice should say Kiswahili words and names (IPA). Without this it reads them as English.
SAY = {"hˈæɾuːə": "hɑːtˈuːɑː", "kwæmbˈoʊkə": "kwɑːmbˈɔːkɑː", "ɐsˈænt": "ɑːsˈɑːntɛ", "sˈɑːnə": "sˈɑːnɑː",
       "pˌiːˌaɪˈɛn": "pˈɪn", "kˈɑːɹɹɪbˌuː": "kɑːɾˈiːbuː", "kəmˈaʊ": "kɑːmˈɑːuː", "kˈæmaʊ": "kɑːmˈɑːuː"}

EPISODES = {
 "teachers": {"label": "For teachers", "scenes": [
  ("intro", "Karibu", None, "Hatua for teachers", "With your guide, Kwamboka", [
    "Hi there, and karibu! I'm Kwamboka.", "I'll be your guide to Hatua.",
    "Give me two minutes, and I'll walk you through it, step by step."]),
  ("signin", "Sign in", "Sign in", None, None, [
    "Let's start by signing in.", ("You're a teacher, so leave it on: I am a teacher.", 3.0),
    ("Type your member number, then your PIN, and press Sign in.", 6.5)]),
  ("today", "Start with Today", "Today", None, None, [
    "This is your Today page.", "It tells you what needs you right now.",
    "Look, the Term 3 results are waiting for you to check."]),
  ("approve", "Check and approve results", "Approve results", None, None, [
    ("So let's check them. Press Check the file.", 4.5), "Hatua shows you what's inside, before anything is saved.",
    ("Happy with it? Press Approve.", 3.0), "Nothing gets into Hatua until you say so."]),
  ("watch", "Learners to watch", "Learners to watch", None, None, [
    ("Now, back to Today.", 2.6), "Hatua has spotted two learners who need a closer look.", ("Let's open Kamau.", 2.6)]),
  ("longview", "The long view", "The long view", None, None, [
    ("Here's Kamau's story, all the way from Grade 4.", 3.4), "We call it the long view.",
    ("Tap any mark, and you'll see the record behind it.", 5.5)]),
  ("comment", "Write a report comment", "Report comment", None, None, [
    ("Report time? Press Write a comment.", 3.6), "Hatua drafts one for you, from Kamau's records.",
    ("You're the teacher, so you decide. If it sounds right, give it a thumbs up.", 6.0)]),
  ("whatsapp", "Message the parent", "Message the parent", None, None, [
    ("Want to tell Kamau's parent? Press Message the parent.", 4.2), "Read the words, and change anything you like.",
    ("Type the parent's WhatsApp number, tick the box, and you're ready to send it yourself.", 8.0),
    ("You press Send, in your own WhatsApp.", 3.4)]),
  ("access", "Give a parent access", "Parent access", None, None, [
    ("Parents can have their own sign-in, too.", 3.2), ("Press Give a parent access, and type the parent's name.", 5.2),
    ("Hatua makes a parent number and a one-time PIN. Print the slip, and hand it over.", 6.0)]),
  ("assistant", "Ask the assistant", "Ask the assistant", None, None, [
    ("Got a question? Just ask the Hatua assistant.", 5.6),
    ("It asks you one quick question first, so the answer fits what you need.", 4.6), ("And it will never rank your learners.", 3.0)]),
  ("look", "Make it yours", "Light or dark", None, None, [
    ("One last thing. In My account, you can switch between light and dark.", 7.0),
    ("And if you ever get stuck, the Help button has the full guide.", 3.6)]),
  ("outro", "You are ready", None, "You are ready", "You stay in charge, step by step", [
    "And that's Hatua.", "You stay in charge, step by step.", "Asante sana, and all the best with your class!"]),
 ]},
 "parents": {"label": "For parents", "scenes": [
  ("intro", "Karibu", None, "Hatua for parents", "With your guide, Kwamboka", [
    "Hello again, and karibu! I'm Kwamboka.", "This one is for you: mum, dad, or guardian.",
    "Let me show you how to follow your child's learning in Hatua."]),
  ("slip", "Get your slip", "Get your slip", None, None, [
    "First, your child's class teacher gives you a small slip.", "It has your parent number, and a one-time PIN.",
    "Hatua lives on the school's computer, so you'll use it at school."]),
  ("signin", "Sign in as a parent", "Sign in", None, None, [
    ("On the sign-in page, choose: I am a parent.", 3.2), ("Type your parent number, and the PIN from your slip.", 6.5),
    ("Then press Sign in.", 2.8)]),
  ("pin", "Choose your own PIN", "Your own PIN", None, None, [
    "The first time, Hatua asks you to choose your own PIN.", ("Pick one that only you know, and type it twice.", 7.0),
    ("From now on, that's your key.", 3.0)]),
  ("child", "Your child's page", "Your child's page", None, None, [
    "And here is your child's page.", "You can see the newest results in every learning area.",
    ("Tap a level, if you'd like to see the record behind it.", 5.5)]),
  ("days", "Days in school, and the teacher's words", "Days and comment", None, None, [
    ("You'll also find the days your child was in school.", 3.6), ("And here is the comment from the class teacher.", 3.6),
    "You only ever see your own child. Nobody else's."]),
  ("pathways", "Pathway ideas", "Pathway ideas", None, None, [
    ("What about senior school pathways?", 3.2),
    "You'll see those ideas only after the teacher has talked them through with you, and opened them."]),
  ("assistant", "Ask a question", "Ask a question", None, None, [
    ("You can also ask the Hatua assistant.", 3.0), ("Try something like: how is my child doing in Mathematics?", 6.5),
    ("It answers from the school's records, and it never compares children.", 5.0)]),
  ("signout", "Sign out", "Sign out", None, None, [
    ("When you're done, always press Sign out.", 3.6), "Other families use this computer, too."]),
  ("outro", "That is all", None, "That is all you need", "You and the teacher, working together", [
    "That's all you need.", "You and the teacher, working together, step by step.", "Asante sana!"]),
 ]},
}


def main(ep: str) -> None:
    k = Kokoro("../video/tts/kokoro.onnx", "../video/tts/voices.bin")
    track, scenes, t = [], [], 0.0
    for sid, title, short, big, sub, lines in EPISODES[ep]["scenes"]:
        u, out = LEAD, []
        for line in lines:
            text, hold = (line, 0) if isinstance(line, str) else line
            ph = k.tokenizer.phonemize(text, "en-us")
            for a, b in SAY.items():
                ph = ph.replace(a, b)
            wav, sr = k.create(ph, voice=VOICE, speed=SPEED, is_phonemes=True)
            assert sr == SR
            d = len(wav) / SR
            out.append({"text": text, "start": round(u, 3), "dur": round(d, 3), "say": ph})
            track.append((t + u, wav))
            u += max(d + GAP, hold)
        dur = round((u - GAP + TAIL) * 30) / 30
        sc = {"id": sid, "title": title, "start": round(t, 4), "dur": dur, "lines": out}
        sc.update({"short": short} if short else {"big": big, "sub": sub})
        scenes.append(sc)
        t += dur
    buf = np.zeros(int(t * SR) + SR, dtype=np.float32)
    for at, wav in track:
        i = int(at * SR)
        buf[i:i + len(wav)] += wav
    sf.write(f"voice-{ep}.wav", buf[:int(t * SR)], SR)
    Path(f"plan-{ep}.json").write_text(json.dumps({"episode": ep, "label": EPISODES[ep]["label"], "total": round(t, 3),
                                                   "voice": VOICE, "scenes": scenes}, indent=1, ensure_ascii=False))
    print(ep, "total", round(t, 1), [(s["id"], round(s["dur"], 1)) for s in scenes])


if __name__ == "__main__":
    main(sys.argv[1])
