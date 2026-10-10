/** Perfil local: nombre, tarjetas y categorías de los movimientos.

Todo se guarda en `app_settings` del equipo. El nombre se usa en el copiloto y
en el sidebar; las categorías se aplican solas al importar un resumen.
*/

import { useEffect, useMemo, useState, type JSX } from "react";

import { Icon } from "../../components/Icon";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "../../components/ui";
import { api } from "../../lib/backend";
import { useAsync } from "../../lib/hooks";
import { useApp } from "../../app/context";

const DEFAULT_BRANDS = ["American Express", "Mastercard", "Visa"];

const DEFAULT_CATEGORIES = [
  "Alimentación",
  "Transporte",
  "Salud",
  "Servicios",
  "Suscripción",
  "Tecnología",
  "Indumentaria",
  "Entretenimiento",
  "Impuestos",
  "Otros",
];

function parseList(raw: string | undefined, fallback: string[]): string[] {
  if (!raw) return fallback;
  try {
    const value = JSON.parse(raw);
    if (Array.isArray(value) && value.length > 0) return value.map(String);
  } catch {
    /* valor viejo o vacío */
  }
  return fallback;
}

export function Profile(): JSX.Element {
  const { toast, refresh, refreshKey, setUserName } = useApp();
  const settings = useAsync(() => api.settings(), [refreshKey]);
  const [name, setName] = useState("");
  const [brands, setBrands] = useState<string[]>(DEFAULT_BRANDS);
  const [categories, setCategories] = useState<string[]>(DEFAULT_CATEGORIES);
  const [newBrand, setNewBrand] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [saving, setSaving] = useState(false);

  const stored = settings.data?.settings;

  useEffect(() => {
    if (!stored) return;
    setName(stored.user_name ?? "");
    setBrands(parseList(stored.user_brands, DEFAULT_BRANDS));
    setCategories(parseList(stored.user_categories, DEFAULT_CATEGORIES));
  }, [stored]);

  const initials = useMemo(() => {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "LP";
    return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
  }, [name]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patchSettings({
        user_name: name.trim(),
        user_brands: JSON.stringify(brands),
        user_categories: JSON.stringify(categories),
      });
      setUserName(name.trim());
      toast("Perfil guardado.");
      refresh();
    } catch (error) {
      toast(error instanceof Error ? error.message : "No se pudo guardar el perfil", "error");
    } finally {
      setSaving(false);
    }
  };

  const addItem = (value: string, list: string[], setList: (next: string[]) => void, reset: () => void) => {
    const clean = value.trim();
    if (!clean) return;
    if (list.some((item) => item.toLowerCase() === clean.toLowerCase())) {
      toast(`«${clean}» ya está en la lista.`, "error");
      return;
    }
    setList([...list, clean]);
    reset();
  };

  const removeItem = (value: string, list: string[], setList: (next: string[]) => void) => {
    setList(list.filter((item) => item !== value));
  };

  if (settings.loading && !settings.data) return <LoadingBlock message="Leyendo tu perfil…" />;
  if (settings.error) return <ErrorBlock message={settings.error} onRetry={settings.reload} />;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">Perfil local · sin sincronización</p>
          <h1>Tu perfil.</h1>
          <p className="heading-copy">
            Con tu nombre la app te habla a vos; las tarjetas y categorías ordenan los resúmenes solos.
          </p>
        </div>
        <button type="button" className="primary-button" onClick={save} disabled={saving}>
          <Icon name="save" /> {saving ? "Guardando…" : "Guardar perfil"}
        </button>
      </div>

      <div className="settings-grid">
        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon mint">
              <Icon name="user" />
            </div>
            <div>
              <h2>Nombre</h2>
              <p>El copiloto te llama por tu nombre y el sidebar lo muestra.</p>
            </div>
          </div>
          <div className="profile-preview">
            <span className="avatar">{initials}</span>
            <div>
              <strong>{name.trim() || "Perfil local"}</strong>
              <small>Datos en tu dispositivo</small>
            </div>
          </div>
          <label className="profile-field">
            <span>¿Cómo te llamás?</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Lautaro" />
          </label>
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon blue">
              <Icon name="credit-card" />
            </div>
            <div>
              <h2>Tarjetas</h2>
              <p>Los emisores que usás: se eligen al revisar un resumen.</p>
            </div>
          </div>
          {brands.length === 0 ? (
            <EmptyState icon="credit-card" title="Sin tarjetas cargadas" body="Agregá Visa, Amex, Mastercard u otra." />
          ) : (
            <ul className="chip-list">
              {brands.map((brand) => (
                <li key={brand}>
                  <span>{brand}</span>
                  <button
                    type="button"
                    aria-label={`Quitar ${brand}`}
                    onClick={() => removeItem(brand, brands, setBrands)}
                  >
                    <Icon name="close" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="inline-add">
            <input
              value={newBrand}
              onChange={(event) => setNewBrand(event.target.value)}
              placeholder="Otra tarjeta (Naranja, Cabal…)"
              aria-label="Agregar tarjeta"
            />
            <button
              type="button"
              className="secondary-button"
              onClick={() => addItem(newBrand, brands, setBrands, () => setNewBrand(""))}
            >
              <Icon name="plus" /> Agregar
            </button>
          </div>
        </Panel>

        <Panel className="settings-card">
          <div className="settings-card-heading">
            <div className="settings-icon yellow">
              <Icon name="list" />
            </div>
            <div>
              <h2>Categorías de movimientos</h2>
              <p>Se aplican automáticamente cuando importás un resumen.</p>
            </div>
          </div>
          {categories.length === 0 ? (
            <EmptyState icon="list" title="Sin categorías" body="Agregá las que uses para clasificar tus consumos." />
          ) : (
            <ul className="chip-list">
              {categories.map((category) => (
                <li key={category}>
                  <span>{category}</span>
                  <button
                    type="button"
                    aria-label={`Quitar ${category}`}
                    onClick={() => removeItem(category, categories, setCategories)}
                  >
                    <Icon name="close" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="inline-add">
            <input
              value={newCategory}
              onChange={(event) => setNewCategory(event.target.value)}
              placeholder="Nueva categoría (Mascotas, Viajes…)"
              aria-label="Agregar categoría"
            />
            <button
              type="button"
              className="secondary-button"
              onClick={() => addItem(newCategory, categories, setCategories, () => setNewCategory(""))}
            >
              <Icon name="plus" /> Agregar
            </button>
          </div>
          <p className="settings-note">
            Cuando el nombre de una categoría aparece en la descripción del consumo (por ejemplo «Petshop Mascotas»),
            se asigna sola. El resto usa las reglas de comercios conocidos.
          </p>
        </Panel>
      </div>
    </>
  );
}
