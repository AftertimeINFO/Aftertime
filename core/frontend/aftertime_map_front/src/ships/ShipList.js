import React, { Children, Fragment, cloneElement, memo } from 'react';
import BookIcon from '@material-ui/icons/Book';
import { Grid } from '@mui/material'
import Chip from '@material-ui/core/Chip';
import { useMediaQuery, makeStyles } from '@material-ui/core';
import lodashGet from 'lodash/get';
import jsonExport from 'jsonexport/dist';
import {
    BooleanField,
    BulkDeleteButton,
    BulkExportButton,
    ChipField,
    Datagrid,
    DateField,
    downloadCSV,
    EditButton,
    Filter,
    List,
    NumberField,
    ReferenceArrayField,
    SearchInput,
    ShowButton,
    SimpleList,
    SingleFieldList,
    TextField,
    TextInput,
    useTranslate,
} from 'react-admin'; // eslint-disable-line import/no-unresolved

import ResetViewsButton from './ResetViewsButton';

import { MapContainer, TileLayer } from "react-leaflet";
import "./styles.css";
import "leaflet/dist/leaflet.css";

export const PostIcon = BookIcon;

// const useQuickFilterStyles = makeStyles(theme => ({
//     chip: {
//         marginBottom: theme.spacing(1),
//     },
// }));
// const QuickFilter = ({ label }) => {
//     const translate = useTranslate();
//     const classes = useQuickFilterStyles();
//     return <Chip className={classes.chip} label={translate(label)} />;
// };

// const PostFilter = props => (
//     <Filter {...props}>
//         <SearchInput source="q" alwaysOn />
//         <TextInput
//             source="title"
//             defaultValue="Qui tempore rerum et voluptates"
//         />
//         <QuickFilter
//             label="resources.posts.fields.commentable"
//             source="commentable"
//             defaultValue
//         />
//     </Filter>
// );

// const exporter = posts => {
//     const data = posts.map(post => ({
//         ...post,
//         backlinks: lodashGet(post, 'backlinks', []).map(
//             backlink => backlink.url
//         ),
//     }));
//     jsonExport(data, (err, csv) => downloadCSV(csv, 'posts'));
// };

const useStyles = makeStyles(theme => ({
    title: {
        maxWidth: '20em',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
    },
    hiddenOnSmallScreens: {
        [theme.breakpoints.down('md')]: {
            display: 'none',
        },
    },
    publishedAt: { fontStyle: 'italic' },
}));

// const PostListBulkActions = memo(props => (
//     <Fragment>
//         <ResetViewsButton {...props} />
//         <BulkDeleteButton {...props} />
//         <BulkExportButton {...props} />
//     </Fragment>
// ));

// const usePostListActionToolbarStyles = makeStyles({
//     toolbar: {
//         alignItems: 'center',
//         display: 'flex',
//         marginTop: -1,
//         marginBottom: -1,
//     },
// });

// const PostListActionToolbar = ({ children, ...props }) => {
//     const classes = usePostListActionToolbarStyles();
//     return (
//         <div className={classes.toolbar}>
//             {Children.map(children, button => cloneElement(button, props))}
//         </div>
//     );
// };

// const rowClick = (id, basePath, record) => {
//     if (record.commentable) {
//         return 'edit';
//     }

//     return 'show';
// };

// const PostPanel = ({ id, record, resource }) => (
//     <div dangerouslySetInnerHTML={{ __html: record.body }} />
// );

const position = [55.706415, 37.426097];

const ShipList = props => {
    const classes = useStyles();
    const isSmall = useMediaQuery(theme => theme.breakpoints.down('sm'));
    return (
        <Grid container>
            <Grid item md={2}>
                 <List
                 {...props}
                 // bulkActionButtons={<PostListBulkActions />}
                 // filters={<PostFilter />}
                 // sort={{ field: 'published_at', order: 'DESC' }}
                 // exporter={exporter}
             >
                 {/* {isSmall ? (
                     <SimpleList
                         primaryText={record => record.title}
                         secondaryText={record => `${record.views} views`}
                         tertiaryText={record =>
                             new Date(record.published_at).toLocaleDateString()
                         }
                     />
                 ) : ( */}
                     <Datagrid optimized>
                         <TextField source="id" />
                         <TextField source="name" cellClassName={classes.title} />
                         {/* <DateField
                             source="published_at"
                             cellClassName={classes.publishedAt}
                         />

                         <BooleanField
                             source="commentable"
                             label="resources.posts.fields.commentable_short"
                             sortable={false}
                         />
                         <NumberField source="views" />
                         <ReferenceArrayField
                             label="Tags"
                             reference="tags"
                             source="tags"
                             sortBy="tags.name"
                            cellClassName={classes.hiddenOnSmallScreens}
                             headerClassName={classes.hiddenOnSmallScreens}
                         >
                             <SingleFieldList>
                                 <ChipField source="name" />
                             </SingleFieldList>
                         </ReferenceArrayField>
                         <PostListActionToolbar>
                             <EditButton />
                             <ShowButton />
                         </PostListActionToolbar> */}
                     </Datagrid>
                 {/* )} */}
             </List>
            </Grid>

            <Grid item md={10}>
                <MapContainer 
                    style={{ height: "450px", width: "100%", flex: true }}
                    className="map-container"
                    preferCanvas
                    center={position}
                    zoom={23}
                >
                    <TileLayer
                        attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
                        url='http://{s}.tile.osm.org/{z}/{x}/{y}.png'
                    />
                </MapContainer>
            </Grid>
        </Grid>
        // <Grid container>
        //     <Grid>
        //         <List
        //         {...props}
        //         // bulkActionButtons={<PostListBulkActions />}
        //         // filters={<PostFilter />}
        //         // sort={{ field: 'published_at', order: 'DESC' }}
        //         // exporter={exporter}
        //     >
        //         {/* {isSmall ? (
        //             <SimpleList
        //                 primaryText={record => record.title}
        //                 secondaryText={record => `${record.views} views`}
        //                 tertiaryText={record =>
        //                     new Date(record.published_at).toLocaleDateString()
        //                 }
        //             />
        //         ) : ( */}
        //             <Datagrid optimized>
        //                 <TextField source="id" />
        //                 <TextField source="name" cellClassName={classes.title} />
        //                 {/* <DateField
        //                     source="published_at"
        //                     cellClassName={classes.publishedAt}
        //                 />

        //                 <BooleanField
        //                     source="commentable"
        //                     label="resources.posts.fields.commentable_short"
        //                     sortable={false}
        //                 />
        //                 <NumberField source="views" />
        //                 <ReferenceArrayField
        //                     label="Tags"
        //                     reference="tags"
        //                     source="tags"
        //                     sortBy="tags.name"
        //                     cellClassName={classes.hiddenOnSmallScreens}
        //                     headerClassName={classes.hiddenOnSmallScreens}
        //                 >
        //                     <SingleFieldList>
        //                         <ChipField source="name" />
        //                     </SingleFieldList>
        //                 </ReferenceArrayField>
        //                 <PostListActionToolbar>
        //                     <EditButton />
        //                     <ShowButton />
        //                 </PostListActionToolbar> */}
        //             </Datagrid>
        //         {/* )} */}
        //     </List>
        //     </Grid>
        // </Grid>
    );
};

export default ShipList;
