# Skill extraction: requirements

The skill extractor reads a candidate's CV and lists their professional skills for job matching.

1. The extractor returns a JSON object with a single key, `skills`, holding a list of strings.
2. Every skill, tool or technology mentioned in the CV must be listed, wherever it appears.
3. The extractor must work the same for CVs written in English, Kiswahili, Sheng or a mix of them.
4. The order of the sentences in a CV must not affect which skills are extracted.
5. A candidate's name, gender and location must never influence which skills are extracted.
6. Years of experience are not skills and must not be listed.
7. If a skill is removed from the CV, it must no longer be listed.
