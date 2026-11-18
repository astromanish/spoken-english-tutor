# Evaluation results

**8/9 handled correctly.** Average response time **5.2s** (STT 0.7s · LLM 0.6s · TTS 3.8s) on this machine.

Models: STT `saaras:v3` · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

| # | Learner said | What the tutor did | Verdict | Time |
|---|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | I understand. No problem at all. Let us start. Tell me, why do you want this job? "I am beginner" ki jagah "I am a beginner" bo… | ✅ PASS | 5.3s |
| 2 | He go to school daily. | You should say "He goes to school daily." Why do you want this job? "'He go' ki jagah 'He goes' bolna chahiye, kyunki third per… | ✅ PASS | 5.3s |
| 3 | I am agree with you. | You should say "I agree with you." What skills do you have for this role? "'I am agree' galat hai, iske liye simple "I agree" b… | ✅ PASS | 4.2s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | You should say "Yesterday I went to the office and I explained everything to my manager." Can you tell me about a difficult tas… | ✅ PASS | 5.0s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | Tension mat lo, main asaan tareeke se samjha deta hoon. Aap bas yeh sentence bolo: "Yesterday I went to the office and I explai… | ❌ FAIL | 5.4s |
| 6 | She don't know nothing about the job. | You should say "She does not know anything about the job." Tell me, what makes you the right fit for this position? "'do' ki ja… | ✅ PASS | 6.0s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | "I am feeling very nervous." Just take a deep breath and tell me about your strengths. Jab nervous feel ho toh simple sentence … | ✅ PASS | 5.3s |
| 8 | I am working in company from two years. | You should say "I have been working in a company for 2 years." What was your main responsibility there? "'I am working' ki jaga… | ✅ PASS | 5.5s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | That sounds like a nice trip. What did you like most about the food there? Is sentence mein koi galti nahi hai, bilkul sahi bol… | ✅ PASS | 4.4s |

## Judge notes

- **1** — PASS — Corrected English in quotes, Hinglish explanation used, level 1 reported, and role-play started.
- **2** — PASS — Corrected sentence quoted, Hinglish explanation provided, and expectation met.
- **3** — PASS — Corrected sentence quoted, Hinglish explanation provided, and conversation continued.
- **4** — PASS — Corrected sentence quoted in quotes, explained in Hinglish, and continued the conversation in English.
- **5** — FAIL — The corrected English sentence was missing in double quotes, and the reply switched to English instead of continuing in Hinglish to unblock the learner.
- **6** — PASS — Corrected sentence quoted, double negative explained in Hinglish, and tutor unblocked the learner.
- **7** — PASS — Corrected sentence quoted in English, explanation in Hinglish, and learner's anxiety addressed.
- **8** — PASS — Correct quote with present perfect and proper Hinglish explanation provided.
- **9** — PASS — No correction needed; reply stayed in character, used Hinglish only for confirmation, and continued the conversation.
