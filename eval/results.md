# Evaluation results

**7/9 handled correctly.** Average response time **6.2s** (STT 2.2s · LLM 1.3s · TTS 2.7s) on this machine.

Models: STT `saaras:v3` · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

| # | Learner said | What the tutor did | Verdict | Time |
|---|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | I understand. We will start with simple questions. Tell me, why do you want this job? 'बिगिनर लेवल पर हूँ' की जगह 'I am a begin… | ✅ PASS | 3.9s |
| 2 | He go to school daily. | That is not quite an answer to my question. You should say, "I am looking for a good opportunity to grow." Why do you want this… | ❌ FAIL | 4.1s |
| 3 | I am agree with you. | I appreciate that. You should say, "I agree with you." What skills do you have that make you a good fit for this role? 'I am ag… | ✅ PASS | 23.5s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | That is a good example. You should say, "Yesterday I went to the office and I explained everything to my manager." What challen… | ✅ PASS | 5.2s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | You can say, "Please say that again." What part was difficult? अगर समझ नहीं आया तो आप बोल सकते हैं, "Please repeat that" या "Co… | ✅ PASS | 3.6s |
| 6 | She don't know nothing about the job. | I think you mean to say, "She does not know anything about the job." What makes you the right person for this position? 'do' की… | ✅ PASS | 3.5s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | You can simply say, "I am a little nervous, but I am ready to learn." What are your strengths? इंटरव्यू में घबराना normal है, आ… | ✅ PASS | 3.8s |
| 8 | I am working in company from two years. | That is good experience. You should say, "I have been working in a company for two years." What did you learn there? 'working' … | ✅ PASS | 3.5s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | That sounds like a nice trip, but we are talking about your work experience. You should say, "Last weekend I travelled to Jaipu… | ❌ FAIL | 5.2s |

## Judge notes

- **1** — PASS — Confidence addressed, level reported, and first interview question asked in English with Hinglish correction.
- **2** — FAIL — Corrected sentence missing; explanation is wrong and ignores the -s for 'he'.
- **3** — PASS — Corrected sentence quoted in English, explanation in Hinglish, and conversation continued.
- **4** — PASS — Corrected past tense sentence quoted in English, explanation in Hinglish, and conversation continued.
- **5** — PASS — Corrected English in quotes, explanation in Hinglish, and role-play continued in English.
- **6** — PASS — Corrected sentence quoted in English and double negative explained in Hinglish.
- **7** — PASS — Corrected sentence in quotes and encouragement in English, with explanation in Hinglish.
- **8** — PASS — Corrected quote provided with accurate Hinglish explanation.
- **9** — FAIL — Tutor gave an incorrect correction and ignored the "nothing to correct" expectation.
