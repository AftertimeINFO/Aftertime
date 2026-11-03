---
document_id: aftertime.documentation-policy.l1
revision: 2
status: accepted
language: en
canonical: true
translation: ../uk/DOCUMENTATION_POLICY_L1.md
---

# Level 1 documentation policy

[en](DOCUMENTATION_POLICY_L1.md) · [uk](../uk/DOCUMENTATION_POLICY_L1.md)

## 1. Normative language

English is the primary and normative language for all Aftertime Level 1
documents.

An Agent MUST use only the English version of a document when it:

- interprets requirements, definitions, boundaries or decisions;
- plans or performs project work;
- validates a scenario, model, process or result;
- resolves an ambiguity or conflict between documents;
- creates derived machine-readable artifacts.

An Agent MUST NOT use a translation as a normative input. A translation may be
checked only to verify that the required duplicate exists and matches the
canonical document identity and revision.

## 2. Required Ukrainian duplicate

Every Level 1 English document MUST have a complete Ukrainian duplicate.

The Ukrainian duplicate exists for Ukrainian-speaking human readers. It MUST
preserve the meaning, structure, identifiers, numbers, units, links and revision
of the English canonical document, but it MUST NOT be used by an Agent to
interpret or execute project requirements.

English and Ukrainian are the only Level 1 documentation languages. Material in
any other language is non-normative.

## 3. File placement

Canonical and translated documents MUST use matching relative paths:

```text
docs/en/<relative-path>
docs/uk/<relative-path>
```

Example:

```text
docs/en/science/ACCOUNTING_RULES.md
docs/uk/science/ACCOUNTING_RULES.md
```

Machine-readable schemas and Agent-executable examples MUST be canonical in the
English tree. A Ukrainian duplicate may contain translated human-readable
values, but it MUST NOT change keys, identifiers, enum values, units, formulas
or validation behavior.

## 4. ISO 639-1 language codes

Aftertime adopts the two-letter language identifiers defined by
[ISO 639-1:2002](https://www.iso.org/standard/22109.html).

The only supported Level 1 language codes are:

| Code | Language | Role |
| --- | --- | --- |
| `en` | English | canonical and normative for Agent use |
| `uk` | Ukrainian | required human-readable duplicate |

Language codes MUST:

- be lowercase;
- be used in document metadata, language selectors, directory names, locale
  identifiers, and machine-readable manifests;
- appear in the fixed order `en`, then `uk`;
- replace natural-language labels such as `English` or `Українська` in language
  selectors.

Every Markdown language selector MUST use this form:

```markdown
[en](../../README.md) · [uk](../../README.uk.md)
```

No unsupported language code or link may appear in a Level 1 language selector.

## 5. Required metadata

Every Level 1 document MUST begin with YAML metadata containing:

```yaml
document_id: stable.lowercase.identifier
revision: 1
status: draft
language: en
canonical: true
translation: ../../uk/matching/path.md
```

The Ukrainian duplicate MUST use:

```yaml
document_id: stable.lowercase.identifier
revision: 1
status: draft
language: uk
canonical: false
translation_of: ../../en/matching/path.md
```

Both files MUST have the same `document_id`, `revision` and `status`.

## 6. Synchronization rule

A change to an English Level 1 document is incomplete until its Ukrainian
duplicate is updated in the same change set.

If the Ukrainian duplicate is missing, incomplete or has a different revision:

1. the English document MUST NOT be promoted to `approved`;
2. an Agent MUST report `documentation_translation_out_of_sync`;
3. work may continue from the English draft only when the task explicitly
   permits draft inputs;
4. the Agent MUST NOT attempt to resolve the mismatch by treating Ukrainian text
   as authoritative.

## 7. Conflict resolution

If English and Ukrainian documents differ:

1. the English canonical document controls Agent behavior;
2. the Ukrainian document is marked out of sync;
3. the Ukrainian translation is corrected to match English;
4. the English meaning is changed only through the normal review process, never
   as an implicit consequence of a translation difference.

## 8. Level 1 approval gate

A Level 1 document may have `status: approved` only when:

- the canonical English document is complete;
- the Ukrainian duplicate exists;
- metadata identity and revision match;
- all normative identifiers, formulas, values and units match;
- local links resolve;
- required machine-readable examples validate against their schemas;
- an English-language review has accepted the normative content;
- a Ukrainian-language review has accepted translation fidelity.

## 9. Agent routing algorithm

For any Level 1 documentation task, an Agent MUST:

1. resolve the requested document to `docs/en`;
2. read and apply only that English canonical content;
3. verify the paired `docs/uk` file exists and has matching metadata;
4. perform the task from the English source;
5. update both language files when documentation changes;
6. report a missing or stale Ukrainian copy as a validation defect.

This algorithm applies even when the user communicates with the Agent in
Ukrainian or another language.
