document.addEventListener("DOMContentLoaded", () => {
  const country = document.querySelector("#country");
  const region = document.querySelector("#region");
  const city = document.querySelector("#city");
  const area = document.querySelector("#area");
  if (!country || !region || !city || !area) return;

  const selected = {region: region.dataset.selected, city: city.dataset.selected, area: area.dataset.selected};
  const selectedCode = (select) => select.selectedOptions[0]?.dataset.code || "";

  function reset(select, placeholder) {
    select.replaceChildren(new Option(placeholder, ""));
    select.disabled = true;
  }

  function populate(select, values, placeholder, selectedValue = "") {
    reset(select, placeholder);
    values.forEach((entry) => {
      const item = typeof entry === "string" ? {name: entry, code: entry} : entry;
      const option = new Option(item.name, item.value || item.name);
      option.dataset.code = item.code;
      select.add(option);
    });
    select.disabled = values.length === 0;
    if (values.some((entry) => (entry.value || entry.name || entry) === selectedValue)) select.value = selectedValue;
  }

  async function load(url) {
    const response = await fetch(url, {headers: {Accept: "application/json"}});
    if (!response.ok) throw new Error("Unable to load location options.");
    return response.json();
  }

  async function updateAreas(selectedValue = "") {
    reset(area, area.dataset.loading || "Loading areas...");
    const query = new URLSearchParams({country: selectedCode(country), region: selectedCode(region), city: city.value});
    populate(area, await load(`/locations/areas?${query}`), area.dataset.placeholder, selectedValue);
  }

  async function updateCities(selectedCity = "", selectedArea = "") {
    reset(city, city.dataset.loading || "Loading cities...");
    reset(area, area.dataset.placeholder);
    const query = new URLSearchParams({country: selectedCode(country), region: selectedCode(region)});
    populate(city, await load(`/locations/cities?${query}`), city.dataset.placeholder, selectedCity);
    await updateAreas(selectedArea);
  }

  async function updateRegions(selectedRegion = "", selectedCity = "", selectedArea = "") {
    reset(region, region.dataset.loading || "Loading regions...");
    reset(city, city.dataset.placeholder);
    reset(area, area.dataset.placeholder);
    const query = new URLSearchParams({country: selectedCode(country)});
    populate(region, await load(`/locations/regions?${query}`), region.dataset.placeholder, selectedRegion);
    await updateCities(selectedCity, selectedArea);
  }

  country.addEventListener("change", () => updateRegions());
  region.addEventListener("change", () => updateCities());
  city.addEventListener("change", () => updateAreas());
  if (country.value) updateRegions(selected.region, selected.city, selected.area);
});
