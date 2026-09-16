# Product: The Game  
  
Rules (Revised Draft)  
  
## 1. Overview  
  
PRODUCT is a web-based, multiplayer, collaborative board game. Players work as one team against the game. The team moves a Portfolio of product Concepts through four stages of development and brings them to market.  
  
**Objective:** Bank at least $1B in Total Addressable Market (TAM) by getting Concepts to Finish within 50 turns.  
  
## 2. Win and Loss Conditions  
  
**The team wins** as soon as the TAM Bank reaches $1B or more. The TAM Bank is the combined TAM of all Concepts that have reached Finish.  
  
**The team loses** if any of the following happens before it wins:  
  
- The 50th turn ends.  
- The last active Concept is removed from the Portfolio, for example by Budget Cuts.  
- A Concept reaches Finish, no active Concepts remain, and the TAM Bank is still under $1B.  
  
**Turn counting:** The 50 turns are counted across the whole team, not per player, so the game runs at the same pace for any number of players. A turn taken with Agile Methods counts as one turn.  
  
## 3. Players and Roles  
  
The game supports 1 to 5 players. There are five roles:  
  
1. Product Manager (PM)  
2. Designer  
3. Engineer  
4. Researcher  
5. Data & ML Engineer  
  
**Assigning roles:** At the start of the game, the PM role goes to a random player. The remaining roles are then dealt at random to the other players. No two players can hold the same role. In a solo game, the player is the PM.  
  
**Team decisions:** Whenever a rule says "the team" decides, the players discuss and the PM makes the final call.  
  
**Role swaps:** A role swap can happen in two ways:  
  
- A Chance card calls for one.  
- The team earns one swap, between any two players, when every active Concept has passed the Product Market Fit Milestone. The swap must be used in the Close phase immediately after it is earned, or it is lost.  
  
## 4. The Board  
  
The board has four quadrants, which are played in this order:  
  
1. Discovery  
2. New Product Development (NPD)  
3. Scaling  
4. Market Maturity  
  
**Loops:** Each quadrant contains a circular loop of 15 coded spaces, three of each of these types:  
  
- Desirability (D)  
- Viability (V)  
- Feasibility (F)  
- Skills  
- Chance  
  
**Gateway spaces:** Each quadrant also has one blank Gateway space outside its 15 coded spaces. The Gateway is where Concepts enter the loop and where they exit it. Landing on a Gateway does not trigger a card draw.  
  
**Milestones:** A Milestone connects each quadrant to the next one:  
  
| Milestone | From | To |  
|---|---|---|  
| Milestone 1 *(name TBD)* | Discovery | NPD |  
| Product Market Fit Milestone | NPD | Scaling |  
| Milestone 3 *(name TBD)* | Scaling | Market Maturity |  
| Milestone 4 *(name TBD)* | Market Maturity | Finish |  
  
**Sharing spaces:** Any number of Concepts can occupy the same space.  
  
## 5. Components and Cards  
  
All cards are public.  
  
- **Role Cards (Beige):** Describe each of the five roles.  
- **Skill Cards (Yellow):** Permanent buffs for players. Some Skills are limited to certain roles.  
- **Concept Cards (Purple):** Individual product Concepts in the Portfolio. Each has DVF token spaces and may have its own modifiers.  
- **Chance Cards (Pink):** Special events that can buff or debuff a Concept, remove Concepts, change the Portfolio, or trigger role swaps. A Chance card may affect roles differently.  
- **Desirability Cards (Green), Viability Cards (Red), Feasibility Cards (Blue):** Together, the DVF cards. They add or remove DVF tokens.  
- **Concept Tokens:** One per Concept, used to track its position on the board.  
- **DVF Tokens:** Placed on Concept cards. The supply is unlimited.  
  
**DVF sub-decks:** Each DVF deck is divided into four sub-decks, one per quadrant. A card is always drawn from the sub-deck that matches the current quadrant of the Concept that landed on the space. The digital version presents each DVF deck as a single pile.  
  
**Empty decks:** When a deck or sub-deck runs out, shuffle its discard pile to form a new draw pile.  
  
## 6. Setup  
  
1. Assign roles as described in Section 3.  
2. Draw 5 Concept cards at random. These make up the starting Portfolio.  
3. Place all 5 Concept Tokens on the Discovery Gateway.  
4. Set every Concept's DVF token count to 0.  
5. Set the TAM Bank to $0 and the turn counter to 0.  
6. The PM takes the first turn. Play then passes clockwise.  
  
## 7. The Portfolio  
  
- **Size:** The Portfolio must always hold between 1 and 5 active Concepts. A Concept that reaches Finish is no longer active and does not count toward this limit.  
- **Entering the board:** New Concepts always enter on the Discovery Gateway.  
- **Removing a Concept:** The Concept goes to the discard pile, and all of its tokens return to the bank. Removal clears negative tokens as well as positive ones, so a Concept in debt can be removed to wipe out its debt.  
  
## 8. Turn Structure  
  
Each turn has three phases.  
  
### 8.1 Move Phase  
  
1. The active player rolls one six-sided die.  
2. The active player chooses one active Concept to move the full amount rolled.  
3. Inside a loop, the player can move the Concept in either direction. Direction can be chosen fresh on every move.  
4. For moving a Concept through a Milestone, see Section 9.  
  
### 8.2 Draw Phase  
  
The Concept that moved triggers the space it lands on:  
  
- **D, V, or F space:** Draw a card from the matching deck (using the sub-deck for the Concept's current quadrant), read it aloud, and apply it to that Concept.  
- **Chance space:** Draw a Chance card and apply it. A Chance card that affects "a Concept" affects the Concept that landed on the space.  
- **Skills space:** The active player draws a Skill card. See Section 10.  
- **Gateway:** No draw.  
  
### 8.3 Close Phase (Portfolio Management)  
  
Before the turn ends, the team (with the PM having final say) may do any number of the following, as long as the Portfolio stays within 1 to 5 active Concepts:  
  
- Keep the Portfolio as it is.  
- Remove Concepts (see Section 7).  
- Draw new Concepts and place them on the Discovery Gateway.  
- Use the team role swap, if it was earned this turn.  
  
When the Close phase is over, the turn counter goes up by 1.  
  
## 9. DVF Tokens and Milestones  
  
### 9.1 Tokens  
  
- Each Concept tracks its own count of D, V, and F tokens.  
- There is no maximum. In the physical game, use a counter or a "3+" marker when a count goes past 3.  
- Counts can go below zero, which represents debt.  
- When a Concept passes a Milestone, all of its tokens reset to 0.  
  
### 9.2 Milestone Conditions  
  
These are the base requirements for exiting each quadrant:  
  
| Quadrant | D | V | F |  
|---|---|---|---|  
| Discovery | 3 | 2 | 1 |  
| New Product Development | 2 | 2 | 2 |  
| Scaling | 1 | 2 | 3 |  
| Market Maturity | 0 | 3 | 2 |  
  
**Checking whether a Concept qualifies:** Work out each dimension separately.  
  
1. Start with the base requirement from the table.  
2. Apply the Concept's multipliers (for example, Platform Play doubles it).  
3. Apply the Concept's additions (for example, User Portal adds +1 D).  
4. Add the Concept's tokens to all Skill buffs that apply to it.  
  
The Concept qualifies when the result of step 4 is at least the result of step 3 in all three dimensions.  
  
Skill buffs count toward these checks but are never placed on the card as physical tokens.  
  
### 9.3 Crossing a Milestone  
  
- A qualifying Concept may pass through the Milestone once its movement reaches or passes the loop's Gateway.  
- Its movement stops on the Gateway of the next quadrant. Any leftover movement is lost.  
- Crossing is optional. The team can leave a qualifying Concept where it is and move other Concepts instead. If the team chooses to move a qualifying Concept, that Concept heads through the Milestone.  
- When a Concept passes Milestone 4, it reaches **Finish**. It then leaves the Portfolio, and its TAM is added to the TAM Bank.  
  
## 10. Skills  
  
**Drawing a Skill:** The active player draws the card.  
  
- **If the card can be used by the active player's role,** the player may take it. A player can hold only one Skill at a time. If the player already has one, the old Skill goes to the discard pile.  
- **If the card cannot be used by the active player's role,** the player chooses one of these:  
 - Discard the card and continue the turn.  
 - Give the card to an eligible teammate. If that teammate already holds a Skill, it is discarded. **The active player's turn then ends immediately, with no Close phase.** The turn still counts toward the 50.  
  
**How Skills work:**  
  
- Skills are permanent until replaced.  
- Every buff from every player's Skill applies to all qualifying Concepts, and all buffs stack.  
  
**Special Skills:**  
  
- **Agile Methods:** The holder takes two complete turns (Move, Draw, and Close each time), which count as one turn toward the 50. This applies on every one of the holder's turns.  
- **Scrum Master:** Once per turn, on the holder's own turn only, the holder may hand the rest of the turn to another player. This can be done at any point in the turn, including right after a card is drawn.  
  
## 11. Card Content (Examples; full inventories to come)  
  
### Skill Cards  
  
1. **Service Designer:** +1 D and +1 F to all Service Concepts. Design role only.  
2. **Experience Designer:** +1 D to all Digital Concepts. Design role only.  
3. **Journey Mapper:** +1 D and +1 F to all Concepts. Design role only.  
4. **User Researcher:** +1 D to all Concepts. Design or Research roles only.  
5. **Venture Capitalist:** +1 V to all Concepts. Product Manager role only.  
6. **Agile Methods:** See Section 10. All roles.  
7. **Scrum Master:** See Section 10. All roles.  
  
### Concept Cards  
  
Every Concept card has:  
  
- A description  
- A TAM value  
- Digital or Physical  
- One or more of Product, Service, and Experience  
- DVF token spaces  
- Any card-specific modifiers  
  
Examples:  
  
1. **Platform Play:** "A two-sided network; twice the work, twice the fun." $5B TAM. Digital. Product + Service + Experience. All DVF Milestone requirements are doubled.  
2. **User Portal:** "The cake is a lie." $0.5B TAM. Digital. Experience. +1 D to all Milestone requirements.  
  
### DVF Cards  
  
Each card is tagged with a quadrant and adds or removes tokens.  
  
- **Smoke Testing** (D): "A cheap way to get signal from noise." Add 1 D token to the Concept.  
  
### Chance Cards  
  
- **Budget Cuts:** The team removes 1 active Concept of its choice. If that was the last active Concept, the team loses.  
  
## 12. Open Items  
  
- Names for Milestones 1, 3, and 4  
- Complete card lists for all decks, including Skills for the Engineer and Data & ML Engineer roles, and Chance cards that treat roles differently  
- The order of the 15 coded spaces within each loop (fixed or randomized)  
- Balance checks through simulation, especially the strength of Agile Methods  
