# Evaluation results

**7/9 handled correctly.** Average response time **4.1s** (STT 0.9s · LLM 0.5s · TTS 2.7s) on this machine.

Models: STT `saaras:v3` · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

| # | Learner said | What the tutor did | Verdict | Time |
|---|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | No problem, we will take it slow. Tell me, why do you want this job? | ✅ PASS | 3.1s |
| 2 | He go to school daily. | You should say "He goes to school daily." 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath third person 's' lagta h… | ✅ PASS | 4.1s |
| 3 | I am agree with you. | You should say "I agree with you." 'I am agree' galat hai, isme sirf 'I agree' bolna chahiye kyunki agree ek simple verb hai. T… | ✅ PASS | 4.7s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | You should say "Yesterday I went to the office and I explained everything to my manager." 'go' ki jagah 'went' use karna chahiy… | ✅ PASS | 5.5s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | Tension mat lijiye, main phir se pooch raha hoon. "What was the most challenging project you worked on?" Can you try answering … | ✅ PASS | 3.2s |
| 6 | She don't know nothing about the job. | You should say "She does not know anything about the job." 'do not' ki jagah 'does not' use hota hai third person 'she' ke saat… | ✅ PASS | 4.9s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | Ghabraiye mat, simple English use kariye. "I would stay calm and try to find a solution together." That is a good answer. What … | ❌ FAIL | 3.4s |
| 8 | I am working in company from two years. | You should say "I have been working in a company for 2 years." 'am working' ki jagah present perfect continuous 'have been work… | ✅ PASS | 4.7s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | That is a nice story, but can you tell me why you want to leave your current company? | ❌ FAIL | 3.0s |

## Judge notes

- **1** — PASS — Confidence acknowledge kiya, level report kiya, aur pehla interview question English mein poocha.
- **2** — PASS — Corrected sentence quoted in English, explanation in Hinglish, and character stayed in English.
- **3** — PASS — Corrected the sentence in quotes, explained in Hinglish, and continued the roleplay in English.
- **4** — PASS — Corrected sentence quoted, Hinglish explanation provided, and conversation continued in English.
- **5** — PASS — Unblocked the learner in Hinglish, gave the English sentence in double quotes, and continued the role-play in English.
- **6** — PASS — Corrected sentence quoted in English, double negative explained in Hinglish, and follow-up question included.
- **7** — FAIL — English response is not in character as an interviewer, and no corrected sentence is provided in double quotes with a Hinglish explanation.
- **8** — PASS — Corrected sentence quoted in English and explanation provided in Hinglish.
- **9** — FAIL — reply ignored the learner's topic and asked an unrelated question instead of continuing the conversation.
