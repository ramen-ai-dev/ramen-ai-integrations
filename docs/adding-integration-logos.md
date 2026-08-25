# Adding Integration Logos

Use this guide whenever a new integration is added to the repository ecosystem
header.

## Standard header

Every plugin README must include:

1. its title;
2. the ramen-ai logo at width `100`;
3. its platform-specific introduction; and
4. the complete centered ecosystem badge row used by the root README.

The root README uses the ramen-ai logo at width `120`. Keep badge order and
markup consistent across the root README, every plugin README, and translated
README companions.

## Badge requirements

Before adding a badge, confirm from the platform's official source:

- the official integration name;
- the brand colour;
- an approved Simple Icons token or licensed artwork;
- the internal plugin directory; and
- any trademark, attribution, or community-disclosure requirements.

Prefer a Shields.io badge using `style=flat`, a descriptive `alt` value, and
`logoColor=white` unless the official artwork requires another treatment.
For example:

```html
<a href="https://github.com/ramen-ai-dev/ramen-ai-integrations/tree/master/plugins/ramen-deepseek-guard">
  <img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
</a>
```

Badge click targets must point to plugin directories in this repository.
External platform links belong in README body text, not in the ecosystem row.

## The current plugin's badge

A plugin README may show its own badge without an `<a>` wrapper because the
reader is already in that plugin directory. Every other README must link that
badge to the plugin directory.

For example, the DeepSeek Harness README uses:

```html
<img src="https://img.shields.io/badge/DeepSeek%20Harness-4D6BFE?style=flat&logo=deepseek&logoColor=white" alt="DeepSeek Harness"/>
```

Its English and Chinese companions use the same unlinked self-badge.

## Artwork files

When Shields.io cannot represent an approved mark:

1. confirm that the artwork may be redistributed;
2. add the scalable source under `assets/` as lowercase kebab-case, such as
   `platform-name-logo.svg`;
3. add a PNG only when a consumer cannot render SVG;
4. record the upstream source and license in the change or adjacent attribution
   document; and
5. use the same repository asset everywhere instead of copying it into plugins.

Plugin-specific screenshots and demonstrations belong under that plugin's own
`assets/` directory. Shared brand marks belong in the root `assets/` directory.

## Community integration disclosures

Follow the host platform's current disclosure policy. DeepSeek Harness requires
community projects to identify themselves prominently as unofficial. Its
plugin category also states that community visibility does not represent
DeepSeek review or endorsement. The English and Chinese DeepSeek Guard READMEs
therefore carry matched notices at the top and link to
[DeepSeek Harness Discussion #2004](https://github.com/deepseek-ai/deepseek-harness/discussions/2004).

## Update checklist

For every new integration:

- [ ] Add the badge to the root `README.md`.
- [ ] Add the badge to every `plugins/**/README*.md` file.
- [ ] Keep the complete badge sequence identical.
- [ ] Leave only each plugin's own badge unlinked where that convention is used.
- [ ] Add the plugin to the root integration table and repository tree.
- [ ] Update every translated README companion.
- [ ] Verify all relative images and internal links resolve.
- [ ] Verify each README contains exactly one badge for the integration.
- [ ] Verify badge click targets do not point to third-party repositories.
- [ ] Record the official artwork source, brand colour, and licensing basis.
