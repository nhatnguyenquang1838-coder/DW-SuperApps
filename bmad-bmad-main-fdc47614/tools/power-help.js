#!/usr/bin/env node
/** Read-only, source-owned help for BMAD. */
const HELP = {
  id: 'bmad',
  name: 'BMAD Method',
  what: 'A structured product and software-delivery lifecycle covering discovery, requirements, planning, architecture, implementation, and review.',
  when: [
    'A new product idea needs structured discovery and requirements.',
    'A project needs PRD, architecture, epics, stories, implementation, or review workflows.',
    'You need to identify the current lifecycle phase and next appropriate skill.',
  ],
  how: [
    'Activate the bmad-help skill in the configured host.',
    'Ask bmad-help what to do next or describe the product/delivery outcome.',
    'Use the installed module catalog to select the next required or optional workflow.',
  ],
  why: 'BMAD provides a repeatable lifecycle and explicit artifacts instead of jumping from an idea directly into unstructured implementation.',
  gives: ['Phase-aware guidance and next-step skills', 'Product, specification, architecture, implementation, and review artifacts', 'Portable routing across configured native hosts'],
  doesNot: ['Put package code in the consumer project', 'Grant branch, pull-request, merge, deployment, approval, secret, or production authority'],
  offline: 'This command renders bundled help only. It does not run npm view, GitHub, release downloads, installers, or project bootstrap.',
  exitCodes: { 0: 'Help rendered', 2: 'Invalid command-line arguments' },
};

function main(argv) {
  const args = argv.slice(2);
  if (args.some((arg) => !['--help', '-h', '--json'].includes(arg))) {
    console.error('Unknown argument. Use --help.');
    return 2;
  }
  if (args.includes('--json')) {
    console.log(JSON.stringify(HELP, null, 2));
    return 0;
  }
  console.log(`BMAD Method (bmad)`);
  for (const key of ['what', 'when', 'how', 'why', 'gives', 'doesNot']) {
    const label = { gives: 'User gets', doesNot: 'Does not' }[key] || key[0].toUpperCase() + key.slice(1);
    console.log(`${label}:`);
    for (const item of Array.isArray(HELP[key]) ? HELP[key] : [HELP[key]]) console.log(`  - ${item}`);
  }
  console.log(`Offline: ${HELP.offline}`);
  console.log('Exit codes:');
  for (const [code, meaning] of Object.entries(HELP.exitCodes)) console.log(`  ${code}: ${meaning}`);
  return 0;
}

process.exitCode = main(process.argv);
