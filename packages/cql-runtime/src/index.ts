/**
 * @oqlos/cql-runtime — public surface for browser bundles and Node services.
 * Canonical runtime documents are OQL v6. Older grammar remains confined to
 * @semcod/oqlts migration internals and the legacy DSL compatibility modules.
 */
export {
  parseOql,
  validateOql,
  simulateOql,
  executeOql,
  executeOqlAst,
  compileOqlHuiProgram,
  migrateOqlToV6,
  migrateDslToV6,
  OQL_MIGRATION_INPUT_VERSIONS,
  RUNTIME_OQL_VERSION,
  runtimeOqlAstVersionIssue,
  runtimeOqlVersionIssue,
  goalBlockHeader,
  funcBlockHeader,
  scenarioDocumentHeader,
} from '@semcod/oqlts';
export type {
  OqlParseResult,
  OqlValidationResult,
  SimulationResult,
  OqlCommand,
  OqlScenario,
  OqlHuiProgram,
} from '@semcod/oqlts';
