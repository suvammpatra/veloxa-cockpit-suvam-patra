# T6a — What Should I Worry About?

## 1. What the CEO asked for

She said:

> "Hi, quick one. I won't type questions every morning, na. When I open it, it should just tell me what to worry about. Top three. Okay, bye."

My understanding is simple: she does not want to type a question every time she uses the cockpit. She wants to see the main concerns as soon as she opens it.

## 2. What I will change

I will make the **What Should I Worry About?** section the first thing she sees when she opens the cockpit.

The question-answering feature will still be available, but she should not have to use it just to find out what needs her attention.

This is not a new feature request. The challenge email already requires a ranked "what should I worry about" view, with every item backed by evidence. T6a makes it clear that this should be the default view.

## 3. Where I would push back

I agree with showing three concerns, but I don't think the system should force itself to find three every time.

If only two concerns have enough evidence behind them, it should show two. Making up a third just to fill the space would defeat the purpose. I also don't want an important concern to disappear simply because it comes fourth.

There is another limitation: the available records currently go up to 31 October 2026. I cannot present the list as if it contains live updates. The cockpit should clearly show the date of the latest available information.

The order should also remain stable when the underlying records have not changed. The same evidence should produce the same ranking. Otherwise, the CEO may see the concerns changing position every time she opens the product without any real reason.

Finally, some concerns may involve individual employees. The cockpit should explain the business risk without exposing personal information that should remain private. If the available evidence cannot be shown safely, the system should say so.

## 4. How I will decide what comes first

I will consider three things when ranking concerns:

1. **Evidence:** How reliable is the information, and how well is it supported by the records?
2. **Impact:** How much money or how many people could be affected?
3. **Trend:** Is the situation getting worse, staying the same, or improving?

The reason for each item's position should be visible. The ranking should be repeatable, so the same records always produce the same order.

## 5. The three concerns based on the records available today

| Rank | What concerns me | Why it matters | Evidence | Confidence |
|---|---|---|---|---|
| 1 | Two backend engineering roles have been on hold since 12 August, and the Atlas launch has moved past its 15 September target. | Engineering speed is already a concern for the CEO, but the two roles that could help address it remain frozen. | `Hiring_Tracker`: REQ-014 and REQ-015 marked "On hold" on 12 August. `06.eml`: "Burn is the priority this quarter." Apr–Jun board update: GA "on 15 September". Jul–Sep board update: "We moved GA". T1 (undated): she was not sure the routing engine would be ready "by the festive season". | High |
| 2 | Engineering engagement has fallen from 3.9 to 3.1 in the Jul–Sep quarter, and the Head of People has raised concern about an engineer. | This could become a delivery risk if an important engineering team member leaves. The records do not show who she means, or that anyone plans to leave. | `Pulse_Survey`: 3.9 to 3.1, with four of five engineers responding in the Jul–Sep round. `11.eml`, 29 September: the Head of People tells the CEO the engineering pulse dropped and suggests Vikram does 1:1s. T3: she says there is one engineer she is worried about, but does not name them. `Leave_Register`: a repeated pattern of approved half-day leave in Engineering in September (person not named here). | Medium |
| 3 | A marketing employee's resignation gives unclear launch timelines as a reason, and the replacement role was still open at the end of October. | The letter does not name Atlas, but Atlas is the only launch in the records. If that is the reason, the delay has already cost the company someone who markets the product, and the replacement is still not complete. | `Resignation_Letter_SM`, 15 September: the employee wanted clearer launch timelines. `Hiring_Tracker`: REQ-016 opened on 17 September, with seven candidates in the pipeline and the role still open at 31 October. | High |

Each of the three expands to the full five-field answer — including its weakest link and what evidence would demote it. The table is the collapsed view; the five fields are what she gets on opening one.

These are the three concerns I would show based on the records currently available. The ranking is based on evidence strength, business impact and the direction of the problem, not simply on which issue sounds most alarming.