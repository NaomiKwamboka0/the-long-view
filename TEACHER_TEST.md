# Hatua: teacher test

Thank you for helping improve Hatua. This 10–15 minute test uses only fictional learners. You are testing whether the review is clear and useful, not evaluating real children.

## Open the demo

1. Extract Hatua-Teacher-Test.zip.
2. Open index.html in a current desktop browser (Chrome, Edge, Firefox or Safari).
3. Start on Teacher test and follow the three activities. No account, internet connection or Python installation is needed after download.

If an email or messaging preview shows a blank page, download and extract the attachment first, then open the HTML file in a browser. Some phones restrict local HTML; use a laptop for this test.

## Try these tasks

- Review Cynthia (HT-0003), follow a Mathematics claim to its source and inspect the long view.
- Enter Test Teacher and approve the original draft. Read English and Kiswahili family messages. Separately approve and download a message. Nothing is sent automatically.
- Review Kiprono (HT-0007), try rejection or editing, and inspect Records to check. A question mark on the long view means a score/level conflict; its term is excluded from patterns.
- Editing a teacher draft locks the prepared family message so that it cannot silently restore what you changed. Use Change my mind, then review the original draft to try the template message again.
- On Teacher test, mark the activities you tried, complete the short feedback form and choose **Email feedback**. Review the prepared email to **ateidiana@gmail.com**, then press Send in your email app. If no email app opens, copy the displayed feedback into an email to that address.
- Open Privacy & data and clear Hatua browser data when finished. Delete downloaded files separately if you no longer need them.

Use Test Teacher, not your real name. Do not enter real learner names, personal stories, school identifiers or other sensitive information.

## Questions for the review

Were the patterns useful and fair? Could you find the evidence? Was approval clear? Did the Kiswahili sound natural? What would prevent you from using this during a family conversation?

## For the person arranging the test

Build a new synthetic-only package with:

    python scripts/package_teacher_demo.py

Share dist/Hatua-Teacher-Test.zip, or just dist/index.html. The package is built in a temporary workspace from the synthetic generator and does not include your existing data, logs or approvals. Do not distribute an arbitrary ui/hatua.html: it embeds whatever class data you built it from.

If you want a web link, the repository includes an optional GitHub Pages workflow. In GitHub Settings → Pages, choose GitHub Actions, then run “Publish synthetic teacher demo” from Actions. This makes the fictional demo public. Use the deployment URL GitHub returns; do not publish a real school export. Hosting can create connection logs even though the app itself has no analytics.

Collect feedback through an agreed private channel. State who will see it and how long you will keep it. Ask permission before recording a test session. This demo has not been validated with real teachers or real school data.
