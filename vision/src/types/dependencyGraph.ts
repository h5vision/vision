export type DependencyEdgeType =
    | 'import'
    | 'reference'
    | 'definition';

export type GraphStatus =
    | 'idle'
    | 'building [Node]'
    | 'building [Edge]'
    | 'ready'
    | 'error';

export interface GraphProgress {
    status: GraphStatus;
    current: number;
    total: number;
    message?: string;
}

export interface DependencyGraphNode {
    id: string;
    path: string;
    label: string;
    language: string;
}

export interface DependencyGraphEdge {
    id: string;
    source: string;
    target: string;
    type: DependencyEdgeType;
}

export interface DependencyGraph {
    version: 1;

    gitCommit: string;

    generatedAt: string;

    nodes: DependencyGraphNode[];

    edges: DependencyGraphEdge[];
}
