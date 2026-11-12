# The teacher portal (whole-school demo)

The portal is a small web page that runs on the teacher's own laptop. Each class teacher signs in with their **member number** and a PIN. They see only their own class, with the full Grade 4 to 9 history of each learner.

Everything in the demo is invented: the school, the 7 teachers and the 100 learners.

## Try it

```
python -m hatua school-demo
```

Then open **http://127.0.0.1:8765** in a browser. Setup takes about 20 seconds. The sign-in page lists the practice accounts. All of them use the PIN `246810`.

To show every challenge requirement step by step, with screenshots, follow [SHOW_THE_REQUIREMENTS.md](SHOW_THE_REQUIREMENTS.md).

| Member number | Teacher | Class | What you will see |
|---|---|---|---|
| M-4001 | Grace Wambui | Grade 4A | Term 3 already approved. Wanjiku (HT-0405) dropped in Kiswahili: an early warning. |
| M-5001 | Peter Otieno | Grade 5A | **A one-time PIN.** Peter must choose his own PIN before anything opens. Then: Term 3 file waiting. |
| M-6001 | Mary Njeri | Grade 6A | Term 3 file waiting. After approval: Kamau (HT-0603) fell two levels in Mathematics, and Atieno (HT-0607) has gone down in English over several terms. |
| M-7001 | John Kiprop | Grade 7A | **No Term 3 file**, so the portal says the file is missing. Upload `demo_school/samples/Grade 7 Term 3 2026 results.xlsx` to try it. |
| M-8001 | Ruth Mwende | Grade 8A | Term 3 file waiting. After approval: Nyokabi (HT-0805) fell in Science. |
| M-9001 / M-9002 | Daniel Mutiso / Agnes Chepkoech | Grade 9A / 9B | One shared Grade 9 file. Each teacher approves only their own stream's rows. Pathway ideas are closed until the teacher opens them. |

Every class has an Excel results file for Term 1 and Term 2 that is already in Hatua. **Delete one of them from the drive folder** and that class's teacher is told.

The demo's date is fixed at 4 November 2026, after Term 3 closed, so Term 3 results are due. Set `HATUA_TODAY` to try another date.

## What a teacher can do

**Today.** What needs the teacher now:
- results that are overdue or waiting for approval;
- learners to watch, grouped by learner;
- for each learner, **Message for the parent**: a short message in English or Kiswahili to copy and send. Hatua sends nothing. The teacher then ticks **I have told the parent** and says how (SMS, WhatsApp, phone call, in person, a note). That way every teacher knows what has already been said.

**School drive.** The whole school shares one drive. It is divided into a folder for each grade, and inside it a folder for each term. Each term folder holds one Excel results file for the class:

```
school_drive/
  Grade 6/
    2026 Term 1/Grade 6 Term 1 2026 results.xlsx
    2026 Term 2/Grade 6 Term 2 2026 results.xlsx
    2026 Term 3/Grade 6 Term 3 2026 results.xlsx
```

- **Excel or CSV.** Hatua reads the first sheet of an `.xlsx` file. Row 1 holds the column names. It needs no extra software and never runs a formula (`hatua/xlsx.py`).
- **Term 1, 2 and 3 at a glance.** Three cards show each term: *In Hatua*, *Waiting for you*, *File missing* or *File gone*.
- A file on the drive is **not** in Hatua until the class teacher checks it and approves it.
- **Check the file** shows how many rows are for the teacher's class, how many are for another class (left for that teacher), and how many cannot be used.
- **Approve** adds only the teacher's own rows. Hatua then checks those learners at once and raises any alerts.
- **Upload** puts a new file into the teacher's own grade folder.
- If a file changes after it was approved, it needs approval again.
- **If a file is deleted or moved**, Hatua tells that class's teacher the next time they look at the portal. See "Alerts: the rules" below.
- The tab shows where the drive folder is on the computer. To use a real shared drive, set `HATUA_DRIVE` to the synced folder on the laptop.

**My class.** Search and filter the class. Each learner page shows:
- alerts, with the records behind them;
- what the records show;
- the long view from Grade 4. Earlier grades are labelled read-only;
- a **comment for the report**.

**School calendar.** Kenya's 2026 term dates from the Ministry of Education, and when each term's results are due in Hatua.

## The Hatua assistant

Press **Hatua assistant**, either at the bottom right of the screen or in the tab row. A chat window opens where the teacher can ask questions in plain English or Kiswahili.

**It asks one question first.** For every new question, even a simple one, Hatua asks one short follow-up question and offers a few answers to tap. Then it answers. This way the answer fits what the teacher needs, and a long answer from Qwen is not wasted on the wrong thing.

| The teacher asks | Hatua asks first | The teacher taps |
|---|---|---|
| "How is Kamau doing?" | "What do you want to know about Kamau?" | Everything the records show / Only what is going down / What to tell the parent |
| "Who needs my attention?" | "Which do you want to see first?" | Learners with an alert / Parents I have not told yet / Results files that are missing or waiting |
| "When does Term 1 open?" | "Which part of the school calendar?" | Term dates / When results are due / KPSEA and KJSEA dates |

- The follow-up question is a fixed rule, so it is instant. Qwen writes the answer.
- The portal will not answer without it. Each follow-up works once, for the teacher who asked.
- The one exception is a question that asks to rank learners. That is refused at once.

Example questions:

- "Who needs my attention this week?"
- "How is Kamau doing, and what should I tell the parent?"
- "When were Term 3 results due?"
- "How do I approve this term's results?"
- "Give me ideas to help a learner who struggles with fractions"

![The assistant asks one question first](guide/16-ask-followup.png)

**The window.** It stays open while you move between tabs.

| To do this | Do this |
|---|---|
| Minimize | Press **–**, or press Esc. It becomes a small button at the bottom right. A dot on the button means a new answer arrived. |
| Maximize or restore | Press **□**, or double-click the title bar. |
| Move it | Drag the title bar. |
| Resize it | Drag the bottom-right corner. |
| Clear the chat | Press the bin. |

The page remembers the window's size and place on this computer. On a phone the assistant opens full screen.

**Who answers.**
- **Qwen 2.5 on the laptop**, through Ollama, when it is running. The window's title bar says which model is answering.
- **Hatua's built-in answers**, when Qwen is off. These cover four things: a learner's progress, who needs attention, the school calendar, and how to use Hatua.

**What it knows.** Every pupil in the teacher's own class: their current patterns, latest levels, alerts and, for Grades 7 to 9, the pathway evidence of learners whose pathway ideas the teacher has opened. Each item carries its record numbers. Pupils named in the question get more detail (the last three terms, attendance, notes). Other classes are never included.

**What keeps it safe.**
- **Only your own class.** The assistant is given only the signed-in teacher's own class. Another class's learners are never in what Qwen sees.
- **Record numbers are checked.** When it talks about a learner's results, it must give record numbers (tap them to open the record). An answer that cites a record it was not given is not shown.
- **Every answer is checked** for labels, rankings and comparisons with classmates. Pathway ideas are allowed, but only as options from the evidence: any answer that tells ("should take STEM"), assigns ("the right pathway for her") or labels ("a STEM learner") is not shown. A failed answer is retried once, then replaced with a built-in answer.
- **Some questions are refused.** A question that asks to rank learners gets a polite fixed reply. So does a pathway question about a learner whose pathway ideas are still closed. The model is not asked at all.
- **It cannot act.** It cannot approve, upload, save or send. It tells the teacher which button to use.
- **The chat is not saved.** The activity log records only that a question was asked, which learners it was about, and who answered. The question and the reply are not logged.

## Senior school pathway ideas

**Closed until the teacher opens them.** The brief says a named person must approve "pathway suggestions before they reach a teacher". So on every learner's page the pathway ideas start closed. The class teacher presses **Open pathway ideas as (their name)**. The button says what they agree to: "I will raise these with the learner and the guardian myself." Hatua writes the teacher's name, the learner and the time in the activity log. Until then the portal sends no pathway ideas for that learner, and the assistant does not have them. An agent token cannot open them.

For learners in **Grade 9**, the learner page and the assistant then show the evidence for each senior school pathway side by side:

| Pathway | Tracks | Junior school learning areas Hatua relates to it |
|---|---|---|
| STEM | Pure Sciences, Applied Sciences, Technical and Engineering, Career and Technical Studies | Mathematics, Integrated Science, Pre-Technical Studies, Agriculture |
| Social Sciences | Languages and Literature, Humanities, Business Science | English, Kiswahili, Social Studies |
| Arts and Sports Science | Visual Arts, Performing Arts, Sports | Creative Arts and Sports |

- **For each pathway**, Hatua lists the cited strengths (held strengths, areas going up, and areas at Meeting Expectations or above now) and the areas to keep building.
- **Fixed order.** The three pathways always appear in the same order. Hatua never orders them by fit, never picks one, and never calls a child "a STEM learner".
- **By grade.** Grades 7 and 8 get the same view labelled *early ideas*, because the choice comes in Grade 9. Grades 4 to 6 get no pathway ideas.
- **Who decides.** The learner chooses, with their family, using their interests, the KJSEA results, the school's career guidance and KNEC's aptitude tests. Pathway ideas stay with the teacher: they are never added to parent messages or report comments, which still block pathway words.
- **The mapping is ours.** It is Hatua's assumption, and a school can change it in `hatua/pathways.py`.

![Pathway ideas, closed](guide/19-pathway-closed.png)

![Pathway ideas, after the teacher opened them](guide/21-pathway-open.png)

This follows the challenge brief. It allows "plain-language subject or career-direction suggestions" that are "age-appropriate, never prescriptive", for "a teacher to raise with the learner and their guardian". It disqualifies "an agent that assigns a track or label".

## Parents

Code: `hatua/family.py`. Practice parents: `P-100001`, `P-100002` (two children), `P-100003` (one-time PIN), PIN `246810`.

- The class teacher gives access from a learner's page. Hatua makes a parent number and a one-time PIN, shown once on a printable slip. To link a brother or sister, the other class teacher types the existing parent number.
- Parents sign in on the same page and follow the same PIN rules as teachers.
- `family.can_view` is the only rule for parents: the learners linked to the parent number that are still on the class list. Every teacher route refuses a parent session (`portal._family` is the only way in).
- A parent sees approved results, days in school, the approved report comment, messages the teacher marked as told, and pathway ideas the class teacher opened. Never teacher notes, unraised alerts, other children or rankings.
- The parent assistant: one follow-up question first, record numbers on every claim, no comparisons, no other children, no pathway ideas before the teacher opens them.
- Audit log: `parent.add`, `parent.remove`, `parent.new_pin`, `family.view`, and the parent's sign-ins.
- Limit: Hatua listens only on 127.0.0.1, so a parent uses the computer where the school runs Hatua. There is no way in from home.

## Comments, and thumbs up or down

1. **Write a comment.** Qwen 2.5 (through Ollama, on the same laptop) writes a two- or three-sentence report comment.
   - The facts come from Hatua's pattern rules, so the model only chooses the words.
   - Every comment is checked: no labels, no comparisons with classmates, no pathway or career advice, no record numbers, and a length limit.
   - If Ollama is not running, or the model's text fails a check, Hatua's fixed template writes the comment. The page says which one wrote it.
2. **Thumbs up, "Sounds right".** The teacher may change a word, then **Use this comment**. Their edit is checked the same way.
3. **Thumbs down, "Doesn't sound right".** The teacher picks why: too harsh, too vague, not accurate, too long or too formal. Hatua writes it again with that in mind.
4. **Learning the teacher's style.** Comments a teacher liked become examples of their tone for the next ones. Their last five thumbs-down reasons stay in mind too.

To use Qwen, start Ollama and pull the model once with `ollama pull qwen2.5:7b`. The portal finds it automatically. Set `HATUA_LLM=off` to always use the template.

## Alerts: the rules

Alerts are fixed rules, not model output. Each one goes only to the learner's class teacher.

| Alert | When |
|---|---|
| File missing | A term's results are due (the term's closing date plus 7 days, from `data/calendar/kenya_2026.json`), and the class's term folder has no results file. |
| File gone | The results are in Hatua, but the file the teacher approved is no longer in the term folder. It was deleted or moved. The results stay safe in Hatua; the school has lost its copy. The alert names the file and the day it was approved. |
| Waiting for approval | The file is in the folder, but the class teacher has not approved it. |
| Early sign | In the newest term, a learning area fell **two rubric levels or more** compared with the term before. The alert says plainly that one term is an early sign, not a pattern. |
| Pattern | Hatua's existing "going down" pattern, now reaching the new term. |

**How a deleted file is noticed.** Hatua looks at the drive folders when a teacher signs in, opens the Today or School drive tab, or comes back to the Hatua window. It does not run in the background. A file alert closes by itself when the file is back, and opens again if the file goes missing again. Putting the very same file back needs no second approval. Each alert is also written to the activity log (`notice.raise`).

For Grades 7 and 8 the alert adds that school results count towards the Grade 9 result, so the file matters.

Hatua still never builds a *pattern* from one result. The early sign exists so the teacher can act **as soon as** the term's results arrive.

## Security

**Signing in**

- **Member number and PIN.** PINs are stored as salted scrypt hashes, never as text (`hatua/auth.py`).
- **A one-time PIN.** A PIN the school hands out works once. The teacher must choose their own PIN before anything opens. Until then every part of the portal answers "Choose your own PIN first".
- **Easy PINs are refused.** At least 6 characters; not numbers in order (123456), not repeats (111111, 121212), not the member number, not a PIN people try first.
- **Lock.** An ID locks for 15 minutes after 5 wrong PINs. A wrong member number gets the same message and takes the same time as a wrong PIN, so nobody can learn which numbers exist.
- **Signed out when not used.** After 15 minutes without use the page signs out and clears the screen. The server ends the sign-in too. A sign-in never lasts more than 8 hours.
- **One place at a time.** A new sign-in with a member number ends that number's sign-in anywhere else.
- **The teacher can see for themselves.** After signing in, the page says when they last signed in, and warns if wrong PINs were tried on their number. **My account** lists their sign-ins, wrong PINs, and what they did in Hatua.
- **Changing a PIN** asks for the current PIN again, and ends every other sign-in of that teacher.

**The page and the server**

- **On this laptop only.** The server listens only on `127.0.0.1`. It refuses requests with another Host header, which defends against DNS rebinding, and requests from another Origin.
- **Nothing from the internet.** The page loads no font, image or script from outside, and its security policy forbids it.
- **The browser.** The session sits in an HttpOnly, SameSite=Strict cookie, so page scripts cannot read it. Every change also needs a CSRF value in a request header.
- **Who sees what.** Decided only by `hatua/scope.py`: a teacher's current learners, with their full history. There is no endpoint that edits a past record.
- **Only a person can approve.** Approving a drive file, opening pathway ideas, rating a comment and recording that a parent was told all need a teacher's sign-in. An agent token is refused, and none of these is an MCP tool.
- **The activity log.** Sign-ins, wrong PINs, sign-outs, PIN changes, uploads, approvals, opened pathway ideas, comment ratings and "parent told" are written to `logs/audit.jsonl`, each line chained to the one before. No PIN is ever written there. A made-up member number is logged as "unknown". Check the chain with `python -m hatua verify-log`.

**What this does not do.** It identifies a teacher among those registered on one computer. It is not TSC or KEMIS sign-on. Anyone who can edit the files on the computer can still change them, so the laptop itself needs a password.

## Limits

- **The calendar.** It holds 2026 only. A school adds `kenya_2027.json` when the Ministry publishes 2027.
- **Deleted files are noticed when someone looks.** Hatua has no background watcher. If nobody opens the portal, nobody is told.
- **Old Excel files.** Hatua reads `.xlsx`. An old `.xls` file must be saved as `.xlsx` first.
- **A forgotten PIN.** The school's Hatua admin gives a new one-time PIN from the terminal (`python -m hatua teacher-add --id M-6001 --name "Mary Njeri" --one-time`). There is no reset inside the portal.
- **Thresholds are guesses.** "Two levels in one term" and "7 days after the term closes" are our assumptions, set for the demo. A teacher should confirm them.
- **No messages are sent.** No SMS or email is sent: the teacher sends the parent message their own way.
- **One computer.** It suits one laptop shared by a school's teachers, or each teacher's own laptop. A server for a whole school would need HTTPS and a head-teacher role. Neither is built.
- **Qwen not run on the build machine.** The model path is tested with a stand-in model that returns both good and bad answers. The screenshots in these docs were taken with Qwen off, so they show Hatua's built-in answers.
