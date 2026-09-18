import type { GameView } from '../types'

export default function TeamPanel({ game }: { game: GameView }) {
  return (
    <section className="panel team-panel">
      <h2>Team</h2>
      <ul className="team-roster">
        {game.players.map((p) => {
          const active = p.id === game.decision_owner
          return (
            <li key={p.id} className={active ? 'team-member active' : 'team-member'}>
              <div className="team-member-header">
                <span className="team-member-id">{p.id}</span>
                <span className="team-member-role">{p.role_id}</span>
              </div>
              <div className="team-member-skill">
                {p.skill_name ? (
                  <>
                    <strong>{p.skill_name}</strong>
                    {p.skill_effect_summary && <span> — {p.skill_effect_summary}</span>}
                  </>
                ) : (
                  <span className="muted">No skill</span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
