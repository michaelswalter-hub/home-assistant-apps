let dragged=null;
function dragMeal(e,el){dragged={recipe_id:el.dataset.id,source_date:el.dataset.date,source_meal:el.dataset.meal};e.dataTransfer.effectAllowed="move"}
async function dropMeal(e,slot){e.preventDefault();if(!dragged)return;await fetch("plan/move",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...dragged,date:slot.dataset.date,meal:slot.dataset.meal})});location.reload()}
async function setMeal(sel){let slot=sel.closest(".slot");await fetch("plan/set",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({date:slot.dataset.date,meal:slot.dataset.meal,recipe_id:sel.value||null})});location.reload()}
