import dagre from '@dagrejs/dagre';

const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

interface GraphNode {
    id: string;
    data: {
        label: string;
        path: string;
        language: string;
    };
    position: {
        x: number;
        y: number;
    };
    style?: Record<string, string>;
}

interface GraphEdge {
    id: string;
    source: string;
    target: string;
    label: string;
}

export function createLayout(nodes: GraphNode[], edges: GraphEdge[]) {
    const graph = new dagre.graphlib.Graph();

    graph.setDefaultEdgeLabel(() => ({}));

    graph.setGraph({
        rankdir: 'TB',
        nodesep: 50,
        ranksep: 100
    });

    nodes.forEach((node) => {
        graph.setNode(node.id, {
            width: NODE_WIDTH,
            height: NODE_HEIGHT
        });
    });

    edges.forEach((edge) => {
        graph.setEdge(
            edge.source,
            edge.target
        );
    });

    dagre.layout(graph);

    const layoutedNodes = nodes.map((node) => {
        const position = graph.node(node.id);

        return {
            ...node,
            position: {
                x: position.x - NODE_WIDTH / 2,
                y: position.y - NODE_HEIGHT / 2
            }
        };
    });

    return {
        nodes: layoutedNodes,
        edges
    };
}