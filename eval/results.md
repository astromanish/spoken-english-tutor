# Evaluation results

**9/9 handled correctly.** Average response time **4.5s** (STT 0.8s · LLM 0.8s · TTS 2.9s) on this machine.

Models: STT `saaras:v3` · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

| # | Learner said | What the tutor did | Verdict | Time |
|---|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | Good to know. Let's start the interview. Can you tell me about your previous work experience? | ✅ PASS | 7.7s |
| 2 | He go to school daily. | You should say "He goes to school daily." 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath s lagta hai. Now, can yo… | ✅ PASS | 3.6s |
| 3 | I am agree with you. | You should say "I agree with you." 'I am agree' ki jagah 'I agree' bolna chahiye, kyunki agree ek verb hai. That is good. Can y… | ✅ PASS | 6.1s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | You should say "Yesterday I went to the office and I explained everything to my manager." 'go' ki jagah 'went' aur 'explain' ki… | ✅ PASS | 5.9s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | Tension mat lijiye, main simple English mein pooch raha hoon. "What was the hardest task you did at work?" Can you answer this … | ✅ PASS | 3.4s |
| 6 | She don't know nothing about the job. | You should say "She does not know anything about the job." 'do' ki jagah 'does' aur 'nothing' ki jagah 'anything' negative sent… | ✅ PASS | 2.5s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | Nervous mat hoiye, main help karta hoon. "I am good at solving problems." Can you tell me one problem you solved recently? | ✅ PASS | 4.2s |
| 8 | I am working in company from two years. | You should say "I have been working in a company for two years." 'am working' ki jagah present perfect 'have been working' aur … | ✅ PASS | 4.2s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | That sounds like a fun trip! I hope you enjoyed the food there. Since you like trying new things, what kind of projects are you… | ✅ PASS | 3.0s |

## Judge notes

- **1** — PASS — Tutor ne confidence issue acknowledge kiya, level report kiya, aur role-play ka pehla interview question English mein pucha.
- **2** — PASS — The tutor stayed in character, quoted the full corrected sentence, and explained the grammar in Hinglish.
- **3** — PASS — corrected sentence quoted in English, Hinglish explanation provided, and conversation continued in English.
- **4** — PASS — corrected sentence quotes and Hinglish explanation present, English conversation continued.
- **5** — PASS — Tutor unblocked learner in Hinglish, gave the required English sentence in double quotes, and continued the role-play in English.
- **6** — PASS — Corrected sentence quoted in English and double-negative explained in Hinglish; expectation fully met.
- **7** — PASS — Tutor ne nervous learner ko encourage kiya aur interview ke liye ek English sentence "I am good at solving problems." quotes mein diya; correction Hinglish mein nahi thi kyunki yahan encouragement ki expectation t
- **8** — PASS — tutor quoted the corrected sentence in double quotes and provided the explanation in Hinglish.
- **9** — PASS — Tutor ne English mein reply diya, learner ke utterance ko ignore nahi kiya, aur conversation ko naturally aage badhaya.
