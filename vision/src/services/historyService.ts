import * as path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import * as vscode from 'vscode';

export class HistoryService {

    private db: DatabaseSync;
    private dbPath: string;

    constructor(dbPath: string) {
        this.dbPath = dbPath;
        this.db = new DatabaseSync(dbPath);
        this.initialize();
    }

    private initialize() {

        this.db.exec(`
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        `);
    }

    public save(
        project_id: string,
        session_id: string,
        role: string,
        content: string
    ) {
        const stmt = this.db.prepare(`
            INSERT INTO chat_history
            (project_id, session_id, role, content)
            VALUES (?,?,?,?)
        `);

        console.log(stmt.run(project_id, session_id, role, content));
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

    public async openDBExternal() {
        const absolutePath = path.isAbsolute(this.dbPath)
            ? this.dbPath
            : path.resolve(this.dbPath);

        const fileUri = vscode.Uri.file(absolutePath);

        try {
            await vscode.commands.executeCommand('revealFileInOS', fileUri);
        } catch (error) {
            console.error('Failed to open DB location in explorer:', error);
        }
    }
}