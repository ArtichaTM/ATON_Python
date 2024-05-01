const form = document.querySelector("#main_form");
const graph = document.querySelector("#graph");
const toastsContainer = document.querySelector('#toasts-container')

var initialized = false;

async function sendData() {
  // Associate the FormData object with the form element
  const formData = new FormData(form);

  try {
    const response = await fetch(fetch_href, {
      method: "POST",
      // Set the FormData instance as the request body
      body: formData,
    });
    if (response.status == 400) {
        response.text().then((text) => {
            document.write(text)
        })
    }
    response.json().then((json) => {
      setGraph(json)
    })
  } catch (e) {
    console.error(e);
  }
}

window.addEventListener('load', (_) => {
  Plotly.newPlot(graph, {info: []})
  for (var i = 0; i < toastsContainer.children.length; i++) {
    bootstrap.Toast.getOrCreateInstance(toastsContainer.children[i]).show()
  }
})

function setGraph(json) {
  console.log("Got: ", json['info'])
  Plotly.react(graph, json['info'], {
    showlegend: true
  })
}

// Take over form submission
form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendData();
});
