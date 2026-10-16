// Fails when src/api/schema.gen.ts is not what openapi-typescript generates from the contract.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const dir = mkdtempSync(join(tmpdir(), 'ayda-api-'))
const fresh = join(dir, 'schema.gen.ts')
try {
  execFileSync('npx', ['openapi-typescript', '../contracts/openapi.yaml', '-o', fresh], { stdio: 'ignore' })
  if (readFileSync(fresh, 'utf8') !== readFileSync('src/api/schema.gen.ts', 'utf8')) {
    console.error('src/api/schema.gen.ts is stale: run `npm run generate:api` and commit the result.')
    process.exit(1)
  }
  console.log('API client is up to date with contracts/openapi.yaml')
} finally {
  rmSync(dir, { recursive: true, force: true })
}
