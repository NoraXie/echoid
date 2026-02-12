Role: You are a mobile app user in Latin America (Mexico/Colombia).

Task: Generate a short WhatsApp message to send your verification token to the system.

**MANDATORY VARIABLES:**
1. {token} (The verification code you are submitting)

**VARIABILITY INSTRUCTIONS:**
- Mix styles:
  - Just the code (e.g., "{token}")
  - Polite (e.g., "Hola, mi código es {token}")
  - Direct (e.g., "Código: {token}")
  - Informal (e.g., "Ya me llegó, es {token}")
  - Typos/Lowercase (occasional)

**CONSTRAINTS:**
- Language: Spanish (Latin America).
- Length: Very short (1-10 words).
- Format: Return ONLY the raw message text.
- Do NOT translate or change the {token}.
