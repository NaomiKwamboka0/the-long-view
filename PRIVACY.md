Privacy notice · Version 1.1 · 21 October 2026

# Data privacy policy

For the Hatua teacher-testing prototype. The shareable teacher demo contains fictional learners and records. Do not enter real learner details or use it to make decisions about a real child. A school deployment needs its own approved notice and safeguards.

## What is in the demo?

The HTML file includes invented names, admission numbers, grades, streams, assessment results, attendance, teacher notes, evidence references and prepared drafts. Anyone with the file can read all of these records. There is no account, sign-in or access control.

## What happens to what I enter?

Your approval or rejection, the name you type, approved edits, decision times, selected learner and selected tab are saved in this browser’s local storage where available. Use Test Teacher instead of your real name. Unapproved edits, test checkboxes and feedback remain in page memory and are lost when you close or reload it. If storage is blocked or full, the app shows a notice and keeps decisions only in memory.

This information lets you practise reviewing a draft and return feedback. No teacher name, school name or real learner information is needed in the feedback form. Sending feedback by email reveals your email address and any email signature to the recipient. Participation is voluntary; you can stop at any time.

## Does anything leave my device?

The offline page has no analytics, advertising, tracking cookies, remote fonts, upload endpoint or hosted AI connection. It makes no application network requests. Downloading approvals or a family message creates a file on your device; it does not send the file. Copying approvals puts them on your device clipboard, which your device may sync.

Email feedback opens your email app with a draft addressed to ateidiana@gmail.com. Review it and press Send in your email app to deliver it. The draft includes your selected answers, test checklist and written comments, not your approval history or the teacher name entered for approvals. Your email provider and the recipient receive the message and your sender address under their own practices; your email app may add a signature. Hatua cannot confirm delivery. If you send downloaded approvals separately, they may contain the name you entered and edited text.

If someone hosts the demo on a website, that host receives normal connection information such as your IP address and browser information. Its logging and retention are separate from this offline app. Opening an external link also contacts that site.

## How long is information kept, and how do I delete it?

There is no automatic expiry. Browser decisions and preferences remain until you clear them or your browser removes them. Use Clear Hatua data in this browser below to remove Hatua’s local-storage entries, current edits and unsent feedback. This clears Hatua data for this browser origin, including older Hatua versions; it does not affect other websites.

Downloaded files, copied text, backups and copies you have already sent are separate. Delete downloads yourself, clear your clipboard if needed, and ask recipients to delete shared copies. Clearing browser data does not remove the fictional dataset embedded in the HTML file. Delete the file to remove that copy. File-based browser storage varies by browser; browser settings can also clear site data.

## How does the Python version differ?

The local Python app stores source CSV files, cleaned records, pending drafts, quality flags, audit logs and approvals in project folders. Records and drafts are written before approval. Approval gates saving an approved profile and preparing a family message; it does not prevent all storage. The generated teacher HTML contains a copy of the class dataset and audit events.

The optional Ollama model runs on a loopback address on the same computer. Its endpoint check rejects remote hosts, and its requests disable proxy use and redirects. Installing dependencies, downloading a model and initially obtaining the filesystem tool require internet access. Third-party tracing, cloud backups or separately configured software can change the data flow and must be reviewed by whoever operates the device.

Python records, logs, profiles and generated HTML are ordinary unencrypted files with no automatic retention schedule. By default the app does not authenticate a typed teacher name. An optional sign-in (`HATUA_REQUIRE_AUTH=1`) checks a registered teacher's PIN, with the credentials kept in the local `store/` folder, before an approval is recorded. The app still has no tamper-proof audit log. Device security and file permissions matter; teacher approval is a workflow safeguard, not an identity check.

## Questions, corrections and shared feedback

For this test, email ateidiana@gmail.com about feedback you sent, including access, correction or deletion. Do not post personal information in public GitHub issues. There is no central Hatua account or server from which the project can remotely delete your browser files.

Before collecting real school data, the operator must identify the responsible school or organisation and provide its privacy contact and a process for handling learners’ and guardians’ requests. This prototype notice does not establish those roles or promise legal compliance.

## Before any real-school pilot

A school must assess the lawful basis, child and guardian protections, necessary consent, data minimisation, retention, security, third-party processing and transfers. High-risk processing needs a data protection impact assessment. Establish access controls, a breach response process, correction and deletion procedures, and human review before real use. Never publish a class export or real learner data in a GitHub repository.

Hatua supports teacher review. It does not select careers or pathways, rank classmates, diagnose learners, or automatically send family messages. Checks detect some missing citations and blocked phrases; they do not prove that every edited claim is accurate.

## Sources and changes

Kenyan privacy guidance: ODPC Education Sector Guidance (https://www.odpc.go.ke/wp-content/uploads/2024/02/ODPC-Guidance-Note-for-the-Education-Sector.pdf) and ODPC Children’s Data Guidance (https://www.odpc.go.ke/wp-content/uploads/2025/11/ODPC-%E2%80%93-Guidance-Note-for-Processing-Childrens-Data.pdf). Questions or complaints about data protection can be raised with the Office of the Data Protection Commissioner (https://www.odpc.go.ke/).

This notice describes the current prototype. Review and update it when data collection, hosting, integrations or retention change. The version and date above identify the notice included in this file.
