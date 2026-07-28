import './style.css'

const GRAPH_URL = '/ua/knowledge-graph.json'

async function load() {
  const log = document.getElementById('log')
  const lines = []

  function write(msg) {
    lines.push(msg)
    log.value = lines.join('\n')
    log.scrollTop = log.scrollHeight
  }

  write('=== UA Power — Development Process Log ===')
  write(`Started at: ${new Date().toISOString()}`)
  write('')

  // Phase 0: Pre-flight
  write('[Phase 0/4] Pre-flight...')
  write('  Resolving PROJECT_ROOT...')
  const projectRoot = window.location.origin
  write(`  PROJECT_ROOT = ${projectRoot}`)
  write('  Resolving UA_DIR...')
  const uaDir = `${projectRoot}/.ua`
  write(`  UA_DIR = ${uaDir}`)
  write('  Checking for existing knowledge-graph.json...')
  write(`  Fetching ${GRAPH_URL}...`)
  write('')

  // Phase 1: Fetch the graph
  write('[Phase 1/4] Fetching knowledge graph...')
  try {
    const resp = await fetch(GRAPH_URL)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const graph = await resp.json()
    write(`  Status: OK (HTTP ${resp.status})`)
    write(`  Graph version: ${graph.version}`)
    write(`  Project: ${graph.project.name}`)
    write(`  Analyzed at: ${graph.project.analyzedAt}`)
    write(`  Commit: ${graph.project.gitCommitHash}`)
    write(`  Mode: ${graph.project.analysisMode}`)
    write('')
    write(`  Found ${graph.nodes.length} nodes`)
    write(`  Found ${graph.edges.length} edges`)
    write(`  Found ${graph.layers?.length ?? 0} layers`)
    write(`  Found ${graph.tour?.length ?? 0} tour steps`)
    write('')

    // Phase 2: Analyze nodes
    write('[Phase 2/4] Analyzing nodes...')
    const byType = {}
    for (const node of graph.nodes) {
      byType[node.type] = (byType[node.type] || 0) + 1
    }
    for (const [type, count] of Object.entries(byType)) {
      write(`  ${type}: ${count}`)
    }
    write('')

    // Phase 3: Analyze edges
    write('[Phase 3/4] Analyzing edges...')
    const byEdgeType = {}
    for (const edge of graph.edges) {
      byEdgeType[edge.type] = (byEdgeType[edge.type] || 0) + 1
    }
    for (const [type, count] of Object.entries(byEdgeType)) {
      write(`  ${type}: ${count}`)
    }
    write('')

    // Phase 4: Summary
    write('[Phase 4/4] Summary...')
    write(`  Languages: ${graph.project.languages?.join(', ') ?? 'N/A'}`)
    write(`  Frameworks: ${graph.project.frameworks?.join(', ') ?? 'N/A'}`)
    if (graph.project.limitations?.length) {
      write('  Limitations:')
      for (const lim of graph.project.limitations) {
        write(`    - ${lim}`)
      }
    }
    write('')
    write('=== Process complete ===')
    write(`Finished at: ${new Date().toISOString()}`)
  } catch (err) {
    write(`  ERROR: ${err.message}`)
    write('')
    write('=== Process failed ===')
  }
}

load()