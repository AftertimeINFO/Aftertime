/* eslint react/jsx-key: off */
import React from 'react';
import { Admin, Resource} from 'react-admin'; // eslint-disable-line import/no-unresolved
import { render } from 'react-dom';
import { Route } from 'react-router-dom';

import comments from './comments';
import CustomRouteLayout from './customRouteLayout';
import CustomRouteNoLayout from './customRouteNoLayout';
import drfProvider, { tokenAuthProvider, fetchJsonWithAuthToken, jwtTokenAuthProvider, fetchJsonWithAuthJWTToken } from 'ra-data-django-rest-framework';
import i18nProvider from './i18nProvider';
import Layout from './Layout';
import posts from './posts';
import ships from './ships';
import users from './users';
import tags from './tags';
import { parseBool } from "./helpers";

// let authProvider;
let dataProvider;
const useJWTAuth = parseBool(process.env.REACT_APP_USE_JWT_AUTH);

console.log('Variable: ',process.env.REACT_APP_API_SERVER_FRONT)

if (useJWTAuth) {
    console.log("Using rest_framework_simplejwt.authentication.JWTAuthentication");
    // authProvider = jwtTokenAuthProvider({obtainAuthTokenUrl: "/api/token/"});
    dataProvider = drfProvider("http://" + process.env.REACT_APP_API_SERVER_FRONT + "/api/v2", fetchJsonWithAuthJWTToken);
} else {
    console.log("Using rest_framework.authentication.TokenAuthentication");
    // authProvider = tokenAuthProvider();
    dataProvider = drfProvider("http://" + process.env.REACT_APP_API_SERVER_FRONT + "/api/v2", fetchJsonWithAuthToken);
}

const initialState = {
    admin: { ui: {sidebarOpen: false, viewVersion: 0}}
}

render(
    <Admin
        // authProvider={authProvider}
        initialState={initialState}
        dataProvider={dataProvider}
        i18nProvider={i18nProvider}
        title="Example Admin"
        layout={Layout}
        customRoutes={[
            <Route
                exact
                path="/custom"
                component={props => <CustomRouteNoLayout {...props} />}
                noLayout
            />,
            <Route
                exact
                path="/custom2"
                component={props => <CustomRouteLayout {...props} />}
            />,
        ]}
    >
        {permissions => [
            // <Resource name="posts" {...posts} />,
            <Resource name="substances" {...ships} />,
            // <Resource name="comments" {...comments} />,
            // permissions ? <Resource name="users" {...users} /> : null,
            // <Resource name="tags" {...tags} />,
        ]}
    </Admin>,
    document.getElementById('root')
);
