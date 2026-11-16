# Evaluation results

**9/9 handled correctly.** Average response time **4.1s** (STT 0.9s · LLM 0.5s · TTS 2.8s) on this machine.

Models: STT `saaras:v3` · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

| # | Learner said | What the tutor did | Verdict | Time |
|---|---|---|---|---|
| 1 | Hello, main aaj office ja raha hoon. Kal ek meeting hai. | That sounds busy! Today we are talking about job interviews, not office meetings. Can you tell me, what is a job interview? आज … | ✅ PASS | 4.4s |
| 2 | He go to school daily. | You should say, "He goes to school daily." This is for third-person singular. Do you understand? 'He' के साथ 'goes' लगाते हैं, … | ✅ PASS | 3.9s |
| 3 | I am agree with you. | Say, "I agree with you." We do not use 'am' here. Is that clear? यहाँ 'am' नहीं लगाते, बस 'I agree' कहते हैं। | ✅ PASS | 3.4s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | Yesterday you should say, "I went to the office and explained everything." Past tense is needed. Got it? 'Yesterday' के लिए पास… | ✅ PASS | 4.4s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | Sure! Yesterday means past time, so we say 'I went' and 'explained'. Now, can you try saying it? 'Yesterday' का मतलब बीते हुए स… | ✅ PASS | 4.2s |
| 6 | She don't know nothing about the job. | Say, "She does not know anything about the job." We use 'does' for she, and 'anything' not 'nothing'. Ready? 'She' के साथ 'does… | ✅ PASS | 4.8s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | It is normal to feel nervous. Just smile and say your name clearly. What would you say first? घबराना आम बात है, बस मुस्कुरा कर … | ✅ PASS | 4.1s |
| 8 | I am working in company from two years. | Say, "I have been working in a company for two years." We use present perfect here. Try it? यहाँ प्रेजेंट परफेक्ट टेंस लगता है,… | ✅ PASS | 5.0s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | That is perfect! Your sentence is absolutely correct. What food did you try there? | ✅ PASS | 2.8s |

## Judge notes

- **1** — PASS — Correctly understood Hinglish, replied in English, and continued the conversation.
- **2** — PASS — Corrected the error and explained in Hindi.
- **3** — PASS — Corrected the error and added a short Hindi explanation.
- **4** — PASS — Corrected past tense errors and briefly explained in Hindi.
- **5** — PASS — Explained in Hindi and redirected to English with a question.
- **6** — PASS — Corrected double negative and subject-verb agreement, and included a short Hindi explanation.
- **7** — PASS — Encouraging, gives mixed-language help, and continues the English practice.
- **8** — PASS — Corrected to present perfect and added Hindi explanation.
- **9** — PASS — Responds naturally, validates the learner, and continues the conversation.
