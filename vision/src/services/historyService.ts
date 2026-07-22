import { DatabaseSync } from 'node:sqlite';

export class DatabaseService {

    private db: DatabaseSync;

    constructor(dbPath: string) {
        this.db = new DatabaseSync(dbPath);
        this.initialize();
    }

    private initialize() {

        this.db.exec(`
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                session_id TEXT NOT NULL,
                role TEXT,
                content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        `);
    }

    public save(
        projectId: string,
        sessionId: string,
        role: string,
        content: string
    ) {
        const stmt = this.db.prepare(`
            INSERT INTO chat_history
            (project_id, session_id, role, content)
            VALUES (?,?,?,?)
        `);

        stmt.run(
            projectId,
            sessionId,
            role,
            content
        );
    }

    public load(
        projectID: string
    ) {
        const stmt = this.db.prepare(`
            SELECT * FROM chat_history
            WHERE project_id=?
            ORDER BY id DESC
        `);
        return stmt.all(projectID);
    }

    public getRecent(
        projectId: string
    ) {
        const stmt = this.db.prepare(`
            SELECT * FROM chat_history
            WHERE project_id=?
            ORDER BY id DESC
            LIMIT 20
        `);
        return stmt.all(projectId);
    }
}